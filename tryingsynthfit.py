# in order to get this array... single object pickle file and unpickle.. itll have the three
# in mcmc_fit and in maybe bd something fit mcmc.py
import time
print(time.ctime())

import pickle
tfile=open('/Users/eeswim/Dropbox/bdnyc_project/TDwarf_spectrum.pkl','rb')
w,f,e=pickle.load(tfile)
# print(w,f,e)
tfile.close()

# get w,f,e array for object then:

import astropy.units as q
w=w*q.um
f=f* q.erg/q.AA/q.cm**2/q.s
e=e* q.erg/q.AA/q.cm**2/q.s

# get model grid from pkl file 

# import pickle
modelfile=open('/Users/eeswim/Dropbox/bdnyc_project/BTSettl_mcmc.pkl','rb')
models=pickle.load(modelfile)
modelfile.close()
print(type(models))

# and then:

import mcmc_fit.mcmc_fit as mc
# mg=mc.make_model_db('btsettl', 'model_atmosphere_db', model_grid=models, grid_data='spec', param_lims=[('teff',400,1600,50),('logg',3.5,5.5,0.5)], fill_holes=False, bands=[], rebin_models=w, use_pandas=False)
mg=models
bdsamp=mc.fit_spectrum([w,f,e], mg, 'btsettl', 'GJ758B', 10*25, 1*50, mask=[], db='', extents=None,object_name='Test', log=False, plot=True, prnt=True, generate=True,outfile=None)

print(time.ctime())

# should come out with... a couple of plots and a couple of pickle files... the pickle files will be the chain that runs...
# will have some file name issues...