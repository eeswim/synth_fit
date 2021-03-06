# Function that interpolates a model
# Includes the ModelGrid class, which 
# 2 December 2013, Stephanie Douglas
################################################################################

import logging

import numpy as np
from astropy import units as u
import matplotlib
matplotlib.use('agg')
import matplotlib.pyplot as plt

from smooth import *

class ModelGrid(object):
    """
    NOTE: at this point I have not accounted for model parameters
    that are NOT being used for the fit - this means there will be 
    duplicate spectra and the interpolation will fail/be incorrect!

    So, for now, params needs to include ALL of the keys in model_dict
    (aside from "wavelength" and "flux")

    Parameters
    ----------
    spectrum: dictionary of astropy.units Quantities
        keys of 'wavelength', 'flux', and 'unc' give the relevant arrays

    model_dict: dictionary
        keys 'wavelength' and 'flux' should correspond to model wavelength and 
        flux arrays, and those should be astropy.units Quantities
        other keys should correspond to params

    params: array of strings
        the model parameters to be interpolated over.  These should 
        correspond to keys of model_dict

    smooth: boolean (default=True)
        whether or not to smooth the model spectra before interpolation 
        onto the data wavelength grid 
        (a check will be performed before interpolation to see if it's
        it's necessary)

    resolution: astropy.units Quantity (optional)
        Resolution of the input DATA, to be used in smoothing the model.
        Only relevant if smooth=True

    snap: boolean (default=False)
        Rather than interpolate between points in the model grid,
        return the model closest to the input parameters. (To make the
        emcee output also stay on the grid, this needs to be set to 
        True in bdfit as well)

    Creates
    -------
    wave (array; astropy.units quantity)
    flux (array; astropy.units quantity)
    unc (array; astropy.units quantity)
    model (dictionary)
    mod_keys (list) : model parameters (from keys of model)
    params (array_like) : parameters to be interpolated over; for now, same as mod_keys
    ndim (integer) : number of params
    plims (dictionary) : limits of each parameter 
    smooth (boolean) 
    interp (boolean)

    """

    def __init__(self,spectrum,model_dict,params,smooth=False,resolution=None,
        snap=False,wavelength_bins=[0.9,1.4,1.9,2.5]*u.um):
        """
        NOTE: at this point I have not accounted for model parameters
        that are NOT being used for the fit - this means there will be 
        duplicate spectra and the interpolation will fail/be incorrect!

        So, for now, params needs to include ALL of the keys in model_dict
        (aside from "wavelength" and "flux")

        Parameters
        ----------
        spectrum: dictionary of astropy.units Quantities
            keys of 'wavelength', 'flux', and 'unc' give the relevant arrays

        model_dict: dictionary
            keys 'wavelength' and 'flux' should correspond to model wavelength and 
            flux arrays, and those should be astropy.units Quantities
            other keys should correspond to params

        params: array of strings
            the model parameters to be interpolated over.  These should 
            correspond to keys of model_dict

        smooth: boolean (default=False)
            whether or not to smooth the model spectra before interpolation 
            onto the data wavelength grid 
            (a check will be performed before interpolation to see if it's
            it's necessary)

        resolution: astropy.units Quantity (optional)
            Resolution of the input DATA, to be used in smoothing the model.
            Only relevant if smooth=True

        snap: boolean (default=False)
            Rather than interpolate between points in the model grid,
            return the model closest to the input parameters. (To make the
            emcee output also stay on the grid, this needs to be set to 
            True in bdfit as well)

        """

        self.model = model_dict
        self.mod_keys = model_dict.keys()
        self.wavelength_bins = wavelength_bins

        ## check that the input model dictionary is formatted correctly
        if ('wavelength' in self.mod_keys)==False:
            logging.info("ERROR! model wavelength array must be keyed with 'wavelength'!")
        if ('flux' in self.mod_keys)==False:
            logging.info("ERROR! model flux must be keyed with 'flux'!")
        if ((type(self.model['wavelength'])!=u.quantity.Quantity) |
            (type(self.model['flux'])!=u.quantity.Quantity) |
            (type(spectrum['wavelength'])!=u.quantity.Quantity) |
            (type(spectrum['flux'])!=u.quantity.Quantity) |
            (type(spectrum['unc'])!=u.quantity.Quantity)):
            logging.info("ERROR! model arrays and spectrum arrays must all"
                + " be of type astropy.units.quantity.Quantity")

        ## Note that the ndim here is just for the MODEL, not everything being fit
        self.params = params
        self.ndim = len(self.params)

        ## Check that all of the parameters listed in params are actually 
        ## included in the model.
        ## Then construct the plims arrays - max and min values on the grid,
        ## along with making sure the parameter values are in numpy arrays
        self.plims = {}
        for p in self.params:
            if (p in self.mod_keys)==False:
                logging.info('ERROR! parameter %s not found!',p)
            else:
                self.plims[p] = {'vals':np.asarray(self.model[p])}
                self.plims[p]['min'] = min(self.plims[p]['vals'])
                self.plims[p]['max'] = max(self.plims[p]['vals'])

        ## smooth==True -> the model has already been matched to the data resolution
        self.smooth = smooth

        ## convert data units to model units (here vs. at every interpolation)
        logging.debug("data units w {} f {} u {}".format(
            spectrum['wavelength'].unit, spectrum['flux'].unit,
            spectrum['unc'].unit))
        logging.debug("model units w {} f {}".format(self.model['wavelength'].unit,
            self.model['flux'].unit))
        self.wave = spectrum['wavelength'].to(self.model['wavelength'].unit)
        self.flux = np.float64(spectrum['flux'].to(self.model['flux'].unit,
             equivalencies=u.spectral_density(self.wave)))
        self.unc = np.float64(spectrum['unc'].to(self.model['flux'].unit,
             equivalencies=u.spectral_density(self.wave)))

        ## Is the first element of the wavelength arrays the same?
        check_diff = self.model['wavelength'][0]-self.wave[0]

        ## If the model and wavelength arrays are the same length
        ## and have the same first element, then don't need to interpolate 
        ## the model onto the data wavelength array
        if ((len(self.model['wavelength'])==len(self.wave)) and 
            (abs(check_diff.value)<1e-10)):
            self.interp = False
            logging.info('NO INTERPOLATION')
        else:
            self.interp = True
            logging.info('INTERPOLATION NEEDED')

        self.is_grid_complete = self.check_grid_coverage()
        if self.is_grid_complete==False:
            self.snap = True
            logging.info("Grid is incomplete; no interpolation on the model grid")
        else:
            logging.info("Grid is complete")
            self.snap = snap
        self.snap = snap

        self.model_flux_units = self.model['flux'][0].unit


    def __call__(self,*args):
        """
        Calculates the probability for the model corresponding to *args
        and returns it (this is what emcee uses when it calls the 
        ModelGrid instance as the lnprob function in bdfit)

        NOTE: at this point I have not accounted for model parameters
        that are NOT being used for the fit - this means there will be 
        duplicate spectra and the interpolation will fail/be incorrect!

        Parameters
        ----------
        *args: array or list
             new parameters. Order and number must correspond to params
        
        Returns
        -------
        lnprob: log of posterior probability for this model + data

        """
        logging.debug(str(args))

        # The first arguments correspond to the parameters of the model
        # the next two, if present, correspond to vsini and rv 
        # ^ vsini/rv are NOT IMPLEMENTED YET
        # the last, always, corresponds to the tolerance
        # the second to last corresponds to the normalization variance
        p = np.asarray(args)[0]
        model_p = p[:self.ndim]
        lns = p[-1]
        norm_values = p[self.ndim:-1]
        logging.debug('params {} normalization {} ln(s) {}'.format(
            model_p,norm_values,lns))

#        if (normalization<0.) or (normalization>2.0):
#            return -np.inf

        normalization = self.calc_normalization(norm_values,#[])
            self.wavelength_bins)

        if (lns>1.0):
            return -np.inf

        ## Check if any of the parameters are outside the limits of the model
        for i in range(self.ndim):
            if ((model_p[i]>self.plims[self.params[i]]['max']) or 
                (model_p[i]<self.plims[self.params[i]]['min'])):
                logging.debug("bad param %s: %f, min: %f, max: %f", 
                    self.params[i],model_p[i],self.plims[self.params[i]]['min'],
                    self.plims[self.params[i]]['max'])
                return -np.inf

        if self.snap:
            # new function that will just get the model from the grid
            # placeholder for now
            mod_flux = self.retrieve_model(model_p)
        else:
            mod_flux = self.interp_models(model_p)

        # if the model isn't found, interp_models returns an array of -99s
#        logging.debug(str(type(mod_flux)))
#        logging.debug(str(mod_flux.dtype))
#        logging.debug(mod_flux)
        if sum(mod_flux.value)<0: 
            return -np.inf

#        mod_flux = mod_flux*normalization

        # On the advice of Dan Foreman-Mackey, I'm changing the calculation
        # of lnprob.  The additional uncertainty/tolerance needs to be 
        # included in the definition of the gaussian used for chi^squared
        # And on the advice of Mike Cushing (who got it from David Hogg)
        # I'm changing it again, so that the normalization is accounted for
        s = np.float64(np.exp(lns))*self.unc.unit
        logging.debug("type unc {} s {} n {}".format(self.unc.value.dtype,
            type(s.value),type(normalization)))
        unc_sq = (self.unc**2 + s**2)  * normalization**2 
#        unc_sq = (self.unc**2) * normalization**2
#        logging.debug("unc_sq {}".format(unc_sq))
        logging.debug("units f {} mf {}".format(self.flux.unit,
            mod_flux.unit))
        flux_pts = (self.flux-mod_flux*normalization)**2/unc_sq
        width_term = np.log(2*np.pi*unc_sq.value)
#        logging.debug("flux+pts {}".format(flux_pts))
#        logging.debug("width_term {} flux pts {} units fp {}".format(
#            np.sum(width_term),np.sum(flux_pts),flux_pts.unit))
        #logging.debug("units wt {}".format(width_term.unit))
        lnprob = -0.5*(np.sum(flux_pts + width_term))
        logging.debug('p {} lnprob {}'.format(str(args),str(lnprob)))
        return lnprob
        

    def interp_models(self,*args):
        """
        NOTE: at this point I have not accounted for model parameters
        that are NOT being used for the fit - this means there will be 
        duplicate spectra and the interpolation will fail/be incorrect!

        Parameters
        ----------
        *args: array or list
             new parameters. Order and number must correspond to params
        
        Returns
        -------
        mod_flux: array
             model flux corresponding to input parameters

        """

        p = np.asarray(args)[0]
        logging.debug('params %s',str(p))

        grid_edges = {}
        edge_inds = {}
        single_flags = np.array([],int)
        # Get the "edge values" - the grid values above and below
        # the desired values
        for i in range(self.ndim):
#            print self.params[i]
#            print self.plims[self.params[i]]['vals']
            if (p[i] in self.plims[self.params[i]]['vals']):
                grid_edges[self.params[i]] = np.array([p[i]])
                edge_inds[self.params[i]] = np.where(
                    self.plims[self.params[i]]['vals']==[p[i]])[0]
                single_flags = np.append(single_flags,i)
            else:
                dn_val = max(self.plims[self.params[i]]['vals'][
                     self.plims[self.params[i]]['vals']<p[i]])
                up_val = min(self.plims[self.params[i]]['vals'][
                     self.plims[self.params[i]]['vals']>p[i]])
#                logging.debug('up {} down {}'.format(up_val,dn_val))
                grid_edges[self.params[i]] = np.array([dn_val,up_val])
                edge_inds[self.params[i]] = np.array([np.where(
                    self.plims[self.params[i]]['vals']==dn_val)[0],np.where(
                    self.plims[self.params[i]]['vals']==up_val)[0]])
#        logging.debug('skipping: {}'.format(single_flags))

        # If all the paramters need to be interpolated (the usual case)
        # then we need 2**ndim spectra (that's how many 'corners' there are)
        # However, we have one less interpolation step for every parameter
        # value that is an existing grid value (i.e. if Teff=1800, we don't
        # need to interpolate because models at that Teff exist in our grid)
        num_spectra = 2**(self.ndim-len(single_flags))
        to_interp = np.delete(range(self.ndim),single_flags)
#        logging.debug('%d spectra', num_spectra)

        # Get the "corners" of the model grid - the model values that
        # will be interpolated between.  This creates a bunch of tuples 
        # (well really, rows in an array) that contain all the unique 
        # combinations of the upper and lower values of each parameter.
        # The values that don't need interpolation only appear once,
        # and for the parameters that need interpolation, half the lines
        # will have the upper value and half will have the lower value.
        grid_corners = np.zeros(num_spectra*self.ndim).reshape(
            num_spectra,self.ndim)
        for i in single_flags:
            grid_corners[:,i] = grid_edges[self.params[i]][0]
        for i in to_interp:  
            if num_spectra==2:
                div_by = 1
            else:
                div_by = 2**(self.ndim-len(single_flags) - i - 1)
            loc = ((np.arange(num_spectra)/div_by) % 2)
            loc1 = np.where(loc==0)[0]
            loc2 = np.where(loc)[0]
#            logging.debug('div_by {} loc1 {} loc2 {}'.format(div_by,loc1,loc2))
            grid_corners[loc1,i] = grid_edges[self.params[i]][0]
            grid_corners[loc2,i] = grid_edges[self.params[i]][1]
#        logging.debug('all corners: %s',str(grid_corners))

        # Get the actual corner spectra to be interpolated
        corner_spectra = {}
        for cpar in grid_corners:
            # cpar contains all the model parameters for a particular spectrum
            # find_i is the location of that spectrum in the dictionary
            find_i = np.ones(len(self.plims[self.params[0]]['vals']),bool)
            for i in range(self.ndim):
                find_i = (find_i & 
                     (cpar[i]==self.plims[self.params[i]]['vals']))
            find_i = np.where(find_i)[0]
#            logging.debug(str(cpar))
            if len(find_i)!=1:
                logging.info('ERROR: Multi/No model {} {}'.format(cpar,find_i))
                return np.ones(len(self.wave))*-99.0*self.flux.unit
#            print find_i
            corner_spectra[tuple(cpar)] = self.model['flux'][find_i]

#        logging.debug('finished getting corner spectra')

        # Interpolate at all paramters requiring interpolation, skip the rest
        old_corners = np.copy(grid_corners)
        old_spectra = dict(corner_spectra)

        for i in range(self.ndim):
#            logging.debug('now dealing with %d %s',i,self.params[i])
            if i in to_interp:
                # get the values to be interpolated between for this loop
                interp1 = old_corners[0,0]
                interp2 = old_corners[len(old_corners)/2,0]
#                logging.debug('lower {}  upper {}'.format(interp1,interp2))

                # coeff expresses how close the new value is to the lower value 
                # relative to the distance between the upper and lower values
                if self.params[i]=='teff':
#                    logging.debug('NEW TEFF COEFF')
                    coeff = (p[i]**4 - interp1**4)*1.0/(interp2**4 - interp1**4)
                else:
                    coeff = (p[i] - interp1)*1.0/(interp2 - interp1)
#                logging.debug('{} coeff {}'.format(self.params[i],coeff))

                # There will be half as many spectra after this.  
                new_corners = old_corners[:len(old_corners)/2,1:]
#                print 'new corners',new_corners
                new_spectra = {}
                for cpar in new_corners:
#                    logging.debug('new params {} {}'.format(cpar, type(cpar)))
                    ns1 = old_spectra[tuple(np.append(interp1,cpar))]
                    ns2 = old_spectra[tuple(np.append(interp2,cpar))]

                    # INTERPOLATE and save
                    new_flux = ns1 + (ns2-ns1)*coeff

                    new_spectra[tuple(cpar)] = new_flux

#                logging.debug(str(new_spectra.keys()))
                old_corners = new_corners
                old_spectra = new_spectra
#                logging.debug('remaining to interp {}'.format(old_spectra.keys()))

            elif i in single_flags:
                # No need to interpolate this variable, so skip it and
                # copy the same spectra to a new dictionary with new indices
                skip_var = old_corners[0,0]
#                print i,self.params[i],skip_var
                new_corners = old_corners[:,1:]
#                print new_corners
                new_spectra = {}
                for cpar in new_corners:
                    new_spectra[tuple(cpar)] = old_spectra[tuple(np.append(
                        skip_var,cpar))]
                old_corners = new_corners
                old_spectra = new_spectra
#                print old_spectra.keys()
            else:
                logging.debug('make_model WTF')
        mod_flux = old_spectra[()][0]
#        logging.debug('all done! %d %d', len(mod_flux), len(self.flux))
#        logging.debug('all done! {} {}'.format(type(mod_flux), type(self.flux)))

        # THIS IS WHERE THE CODE TAKES A LONG TIME
        if self.smooth:
#            logging.debug('starting smoothing')
            mod_flux = falt2(self.model['wavelength'],mod_flux,resolution) 
#            logging.debug('finished smoothing {}'.format(type(mod_flux)))
#        else:
#            logging.debug('no smoothing')
        if self.interp:
#            logging.debug('starting interp')
            mod_flux = np.interp(self.wave,self.model['wavelength'],mod_flux)
#            logging.debug('finished interp')

        mod_flux = self.normalize_model(mod_flux)

        if type(mod_flux)!=u.quantity.Quantity:
            mod_flux = mod_flux*self.model_flux_units

#        logging.debug('returning {}'.format(type(mod_flux)))
        return mod_flux

    def normalize_model(self,model_flux,return_ck=False):
        # Need to normalize (taking below directly from old makemodel code)
        #This defines a scaling factor; it expresses the ratio 
        #of the observed flux to the model flux in a way that  
        #takes into account the entire spectrum.  
        #The model spectra are at some arbitrary luminosity;
        #the scaling factor places this model spectrum at the same
        #apparent luminosity as the observed spectrum.     
#         mult1 = self.flux*model_flux
#         bad = np.isnan(mult1)
#         mult = np.sum(mult1[~bad])
#         #print 'mult',mult                                 
#         sq1 = model_flux**2
#         square = np.sum(sq1[~bad])
#         #print 'sq',square                                 
#         ck = mult/square
#         #print 'ck',ck                                     
#         #Applying scaling factor to rescale model flux array
#         model_flux = model_flux*ck
#        logging.debug('finished renormalization') 

        mult1 = sum(self.flux*model_flux/(self.unc**2))
        mult = sum(model_flux*model_flux/(self.unc**2))
        ck = mult1/mult
        model_flux = model_flux*ck
        
        if return_ck:
            return model_flux, ck
        else:
            return model_flux


    def check_grid_coverage(self):
        """ checks if every parameter permutation has a corresponding model """

        unique_params = [np.unique(self.plims[self.params[i]]["vals"]) for 
                         i in range(self.ndim)]

        # calculate the number of possible permutations 
        ncomb = 1 
        for i in range(self.ndim):
            ncomb = ncomb * len(unique_params[i])

        unique_combinations = np.zeros(ncomb*self.ndim).reshape((ncomb,self.ndim))

        for i in range(self.ndim):
            div_by = 2**(self.ndim - i - 1)
            loc = ((np.arange(ncomb)/div_by) % len(unique_params[i]))
            for j in range(len(unique_params[i])):
                loc_j = np.where(loc==j)[0]
                unique_combinations[loc_j,i] = unique_params[i][j]

        is_grid_full = True
        for i, up in enumerate(unique_combinations):
            p_loc = np.arange(len(unique_combinations))
            for j in range(self.ndim):
                p_loc = np.intersect1d(p_loc,np.where(
                     self.plims[self.params[i]]["vals"]==up[j])[0])
            if len(p_loc)==0:
                logging.info("UNEVEN GRID")
                is_grid_full = False
                break
            else:
                continue

        return is_grid_full


    def find_nearest(self,arr,val):
        """
        Finds the *locations* (indices) in an array (arr) 
        that are closest to a given value (val)

        This only works when the entire grid is filled and evenly spaced
        """

        close_val = arr[np.abs(arr-val).argmin()]
        logging.debug("{} nearest {}".format(val,close_val))

        indices = np.where(np.abs(arr-close_val)<=1e-5)[0]
        return indices

    def find_nearest2(self,param_arrays,p_values):
        """
        finds the set of model parameters in param_arrays that is
        closest to the values give in p_values

        Parameters
        ----------
        param_arrays: array-like (n_models, ndim)

        p_values: array-like (ndim)

        """

        min_distance = 1e10
        matched_i = -99
        for i, mod_params in enumerate(param_arrays):
#            logging.debug("mod_p {} p_val {}".format(mod_params,p_values))
            mod_difference = abs(np.array(mod_params) - np.array(p_values))
            check_distance = np.average(mod_difference)
            if check_distance==min_distance:
                logging.debug("MULTIPLE MODELS FOUND {}".format(p_values))
            elif check_distance<min_distance:
                min_distance = check_distance
                matched_i = i
            else:
                continue

        return matched_i

    def retrieve_model(self,*args):
        """
        NOTE: at this point I have not accounted for model parameters
        that are NOT being used for the fit - this means there will be 
        duplicate spectra!

        Parameters
        ----------
        *args: array or list
             new parameters. Order and number must correspond to params
        
        Returns
        -------
        mod_flux: array
             model flux corresponding to input parameters

        """

        p = np.asarray(args)[0]
#        logging.debug('starting params %s',str(p))

        # p_loc is the location in the model grid that fits all the 
        # constraints up to that point. There aren't constraints yet,
        # so it matches the full array.
        p_loc = range(len(self.model['flux']))

        if self.is_grid_complete:
            for i in range(self.ndim):
                # find the location in the ith parameter array corresponding
                # to the ith parameter
                this_p_loc = self.find_nearest(self.model[self.params[i]],p[i])

                # then match that with the locations that already exist
                p_loc = np.intersect1d(p_loc,this_p_loc)
        else:
            num_models = len(self.plims[self.params[0]]["vals"])
            param_arrays = [[self.plims[self.params[i]]["vals"][j]
                for i in range(self.ndim)] for j in range(num_models)]
            p_loc = [self.find_nearest2(param_arrays,p)]

        logging.debug(str(p_loc))
        mod_flux = np.ones(len(self.wave))*-99.0*self.flux.unit
        if len(p_loc)==1:
            mod_flux = self.model['flux'][p_loc]
            while len(mod_flux)==1:
                mod_flux = mod_flux[0]
        else:
            logging.info("MODEL NOT FOUND/DUPLICATE MODELS FOUND!!")
            logging.info("params {} location(s) {}".format(p, p_loc))
            return mod_flux

        if self.smooth:
#            logging.debug('starting smoothing')
            mod_flux = falt2(self.model['wavelength'],mod_flux,resolution) 
#            logging.debug('finished smoothing')
#        else:
#            logging.debug('no smoothing')
        if self.interp:
            logging.debug('starting interp {} {} {}'.format(len(self.wave),
                len(self.model['wavelength']),len(mod_flux)))
            mod_flux = np.interp(self.wave,self.model['wavelength'],mod_flux)
            logging.debug('finished interp')

        mod_flux = self.normalize_model(mod_flux)

        if type(mod_flux)!=u.quantity.Quantity:
            mod_flux = mod_flux*self.model_flux_units

#        logging.debug('returning {}'.format(type(mod_flux)))
        return mod_flux

    def snap_full_run(self,cropchain):
        """
        """
        new_cropchain = np.copy(cropchain)
        round_is_valid = False
        for i in range(self.ndim):
            check = np.unique(np.diff(np.unique(self.model[self.params[i]])))
            if len(check)!=1:
                round_is_valid=False
                logging.info("can't round {}".format(self.params[i]))
                break
            else:
                round_is_valid=True
                logging.info("{} ok to round".format(self.params[i]))
                continue

        logging.info("Starting to snap chains")
        if round_is_valid and self.is_grid_complete:
            def my_round(x,base):
                return np.round(base * np.round(x / base),2)

            for i in range(self.ndim):
                base_i = np.unique(np.diff(np.unique(self.model[self.params[i]]
                    )))[0]
                new_cropchain[:,i] = my_round(cropchain[:,i],base_i)
            logging.info("Finished rounding chains")
        else:
            num_models = len(self.plims[self.params[0]]["vals"])
            param_arrays = [[self.plims[self.params[i]]["vals"][j]
                for i in range(self.ndim)] for j in range(num_models)]
            for j,p_all in enumerate(cropchain):
                p = p_all[:self.ndim]
#                logging.debug('starting params %s',str(p))
                p_loc = self.find_nearest2(param_arrays,p)

                for i in range(self.ndim):
#                    logging.debug("i {} p[i] {}".format(i,self.model[self.params[i]][p_loc]))
                    new_cropchain[j,i] = self.model[self.params[i]][p_loc]
#                logging.debug("snapped params {}".format(new_cropchain[j]))
            logging.info("Finished snapping chains")

        return new_cropchain


    def calc_normalization(self,n_values,
        wavelength_bins=[0.9,1.4,1.9,2.5]*u.um):
        """
        calculates normalization as a function of wavelength

        Parameters
        ----------
        n_values: array or list
            normalization values for the regions given by wavelength_bins
    
        wavelength_bins: array or list
            the wavelength bins corresponding to n_values
            length should be one longer then n_values
            the normalization for wavelengths below and above the minimum
            and maximum bin edges will be set to the same as the nearest bin


        Returns
        -------
        normalization: array
            normalization values as a function of wavelength
            corresponding to self.wave

        """

        normalization = np.zeros(len(self.wave))

        if len(wavelength_bins)==0:
            normalization[:] = n_values
        else:
            for i in range(len(n_values)):
                norm_loc = np.where((self.wave>wavelength_bins[i]) &
                    (self.wave<=wavelength_bins[i+1]))[0]
                normalization[norm_loc] = n_values[i]
            norm_loc = np.where(self.wave<=wavelength_bins[0])[0]
            normalization[norm_loc] = n_values[i]
            norm_loc = np.where(self.wave>wavelength_bins[-1])[0]
            normalization[norm_loc] = n_values[i]

        return normalization
