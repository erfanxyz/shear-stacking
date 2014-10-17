#!/bin/env python

import numpy as np
import esutil as eu
import pyfits
from sys import argv
from os.path import exists
from os import system
from common import *
from glob import glob
from math import pi

def getValues(data, key):
    # what values are used for the slices
    if callable(key):
        return key(data)
    else:
        return data[key]

def getSliceMask(values, lower, upper, return_num=False):
    if return_num is False:
        return (values >= lower) & (values < upper)
    else:
        return sum((values >= lower) & (values < upper))

def saveStack(outdir, DeltaSigma, DeltaSigma_cross, radius, weight, keys, splittings, slices, last_element):
    np.save(outdir + "/DeltaSigma.npy", DeltaSigma[:last_element['all']])
    np.save(outdir + "/DeltaSigma_cross.npy", DeltaSigma_cross[:last_element['all']])
    np.save(outdir + "/weight.npy", weight[:last_element['all']])
    np.save(outdir + "/radius.npy", radius[:last_element['all']])
    keynames = []
    for k in keys:
        if callable(k):
            key_name = k.__name__
        else:
            key_name = k
        keynames.append(key_name)
        for vv in slices[key_name].keys():
            filename = key_name + "_%d" % vv + ".npy"
            np.save(outdir + "/" + filename, slices[key_name][vv][:last_element[key_name][vv]])
    np.save(outdir + "/splittings.npy", splittings)
    np.savetxt(outdir + "/keynames.txt", keynames, fmt='%s')

# get separation in deg for distance L in Mpc/h at redshift z
# uses c/H0 = 3000 Mpc/h
def Dist2Ang(L, z):
    global cosmo
    return L / cosmo.Da(z) / 3000. * 180./math.pi

def Ang2Dist(theta, z):
    global cosmo
    return theta * cosmo.Da(z) * 3000. / 180. * math.pi

def B_D(data):
    return data['im3shape_' + band.lower() + '_bulge_flux'] / data['im3shape_' + band.lower() + '_disc_flux']

if __name__ == '__main__':
    if len(argv) < 5:
        print "usage: " + argv[0] + " <lens catalog> <shape catalog> <band> <output label> [tmpdir]"
        exit(1)

    lensfile = argv[1]
    shapefile = argv[2]
    band = argv[3]
    label = argv[4]
    if len(argv) > 5:
        tmpdir = argv[5]
    else:
        tmpdir = "/tmp/"
    
    coords = "angular"
    lens_z_key = 'Z_LAMBDA'
    shape_z_key = 'ZP'
    shape_ra_key = 'ALPHAWIN_J2000_' + band.upper()
    shape_dec_key = 'DELTAWIN_J2000_' + band.upper()
    
    # keys = [shape_z_key, 'im3shape_' + band.lower() + '_snr', 'im3shape_' + band.lower() + '_radius', 'im3shape_' + band.lower() + '_stamp_size']
    # splittings = [[0.7, 0.9, 1.1, 1.5], [20,40,60,1000], [0.263,0.789,26.3], [32,48,64,128]]
    
    #keys = ['im3shape_' + band.lower() + '_info_flag']
    #splittings = [[0,1,8,128,1024, 2**21]]

    keys = ['im3shape_' + band.lower() + '_bulge_flux', 'im3shape_' + band.lower() + '_disc_flux', B_D, 'im3shape_' + band.lower() + '_mask_fraction']
    splittings = [3, 3, 3, [0., 0.2, 0.4, 1]]
    
    outdir = tmpdir + "/" + label
    system('mkdir -p ' + outdir)

    if coords == "physical":
        maxrange = 5. # Mpc/h
    else:
        maxrange = 1.1  # deg

    matchfile = outdir + '/matches_' + band.lower() + '.bin'
    stackfile = outdir + "/DeltaSigma.npy"

    if exists(stackfile) is False:
        # open lens catalog, apply selection if desired
        hdu = pyfits.open(lensfile)
        lenses = hdu[1].data
        #good_cl = (lenses[lens_z_key] < 0.6)
        #lenses = lenses[good_cl]
        
        if coords == "physical":
            maxrange = Dist2Ang(maxrange, lenses[lens_z_key])
        print "lens sample: %d" % lenses.size

        # open shapes, apply post-run selections
        shdu = pyfits.open(shapefile)
        good_sh = ModestSG(shdu[1].data) & (shdu[1].data['im3shape_' + band.lower() + '_exists'] == 1) & (shdu[1].data['im3shape_' + band.lower() + '_error_flag'] == 0) & (shdu[1].data['im3shape_' + band.lower() + '_info_flag'] == 0) & (shdu[1].data['FLAGS_' + band.upper()] == 0)
        shapes = shdu[1].data[good_sh]
        print "shape sample: %d" % shapes.size

        # find all galaxies in shape catalog within maxrange arcmin 
        # of each lens center
        print "matching lens and source catalog..."
        if exists(matchfile) is False:
            # CAVEAT: make sure to have enough space where you put the match file
            # it has 24 byte per match, which quickly becomes Gb's of data 
            h = eu.htm.HTM(8)
            h.match(lenses['RA'], lenses['DEC'], shapes[shape_ra_key], shapes[shape_dec_key], maxrange, maxmatch=-1, file=matchfile)
            del h
        else:
            print "  re-using existing matchfile", matchfile

        htmf = HTMFile(matchfile)
        print "  found ", htmf.n_matches, "matches"


        # set up the container for the shears
        Ngal = htmf.n_matches
        DeltaSigma = np.empty(Ngal, dtype='float32')
        DeltaSigma_cross = np.empty(Ngal, dtype='float32')
        radius = np.empty(Ngal, dtype='float32')
        weight = np.empty(Ngal, dtype='float32')

        # define the slices and set up their index containers
        # can be any key in the shape catalog or a function thereof
        slices = {}
        print "determining slice ranges..."
        for i in range(len(keys)):
            if callable(keys[i]):
                key_name = keys[i].__name__
            else:
                key_name = keys[i]
            slices[key_name] = {}
            # FIXME: there is no selection on the shapes here, e.g. no BG cut
            values = getValues(shapes, keys[i])
            # if the slices are set already: find out how many source will fall in each
            if iterable(splittings[i]):
                for s in range(len(splittings[i])-1):
                    Ngal_slice = getSliceMask(values, splittings[i][s], splittings[i][s+1], return_num=True)*(1.*Ngal)/len(shapes)
                    slices[key_name][s] = np.zeros(Ngal_slice, dtype='int64')
            # for percentile splits: create equal-size containers and determine limits
            else:
                for s in range(splittings[i]):
                    # CAVEAT: this is not exactly correct, but deviations
                    # should be minimal for large stacks
                    # -> Check for the size of the contained before filling it!
                    slices[key_name][s] = np.zeros(Ngal/splittings[i], dtype='int64')
                # remove 2.5% on either side to reduce impact of outliers
                delta = 95./splittings[i]
                ranges = [2.5 + k*delta for k in range(splittings[i]+1)]
                splittings[i] = percentile(values, ranges)
                del ranges
            del values
            print "  " + key_name + ":", splittings[i]

        # remember the last element (of the whole array DeltaSigma) for each
        # of the slices
        last_element = {'all': 0}
        for k,v in slices.iteritems():
            last_element[k] = {}
            for vv in v:
                last_element[k][vv] = 0

        # iterate over all lenses
        print "stacking lenses..."
        specz_calib = getSpecZCalibration()
        counter = 0
        for m1, m2, d12 in htmf.matches():
            lens = lenses[m1]
            shapes_lens = shapes[m2]

            # compute effective Sigma_crit
            z_phot, cz = getSigmaCritCorrection(specz_calib, lens[lens_z_key])
            sigma_crit = getSigmaCritEffective(z_phot, cz, shapes_lens[shape_z_key])
            # determine extent in DeltaSigma array
            lower, upper = last_element['all'], last_element['all'] + len(m2)
            elements = np.arange(lower, upper, dtype='int64')
            DeltaSigma[lower:upper], DeltaSigma_cross[lower:upper] = sigma_crit * tangentialShear(shapes_lens[shape_ra_key], shapes_lens[shape_dec_key], shapes_lens['im3shape_' + band.lower() + '_e1'], -shapes_lens['im3shape_' + band.lower() + '_e2'], lens['RA'], lens['DEC'], computeB=True)
            if coords == "physical":
                radius[lower:upper] = Ang2Dist(np.array(d12), lens[lens_z_key])
            else:
                radius[lower:upper] = d12
            weight[lower:upper] = 0.2/(0.2**2 + (0.1*20/shapes_lens['im3shape_' + band.lower() + '_snr'])**2)**0.5/sigma_crit**2
            last_element['all'] += len(m2)

            # get indices for all sources in each slice
            for i in xrange(len(keys)):
                if callable(keys[i]):
                    key_name = keys[i].__name__
                else:
                    key_name = keys[i]
                values = getValues(shapes_lens, keys[i])
                for s in xrange(len(splittings[i])-1):
                    mask = getSliceMask(values, splittings[i][s], splittings[i][s+1])
                    sum_mask = sum(mask)
                    # check if slice array can keep all indices
                    # if not, double its size
                    if last_element[key_name][s] + sum_mask > slices[key_name][s].size:
                        slices[key_name][s].resize(max(slices[key_name][s].size * 2,last_element[key_name][s] + sum_mask))
                        print " (extending slice index list for %s[%d])" % (key_name, s)
                    slices[key_name][s][last_element[key_name][s] : (last_element[key_name][s] + sum_mask)] = elements[mask]
                    last_element[key_name][s] += sum_mask
                    del mask
                del values
            del shapes_lens, elements, z_phot, cz, sigma_crit

            # output status update and do backup
            save_chunks = lenses.size / 10
            if counter % 100 == 0:
                print '  lens %d, matched %.2f%%' % (counter, upper*100./htmf.n_matches)
            if htmf.n_matches > 5e8 and counter > 0 and counter % save_chunks == 0:
                print '  saving stack backup...'
                saveStack(outdir, DeltaSigma, DeltaSigma_cross, radius, weight, keys, splittings, slices, last_element)
            counter += 1

        # reduce the size of the containers to last_element
        DeltaSigma.resize((last_element['all']), refcheck=False)
        DeltaSigma_cross.resize((last_element['all']), refcheck=False)
        weight.resize((last_element['all']), refcheck=False)
        radius.resize((last_element['all']), refcheck=False)
        if coords != "physical":
            radius *= 60 # distances now in arcmin
        for k,v in slices.iteritems():
            for vv in v.keys():
                slices[k][vv].resize((last_element[k][vv]), refcheck=False)

        # save the entire shebang
        print "saving stack files"
        saveStack(outdir, DeltaSigma, DeltaSigma_cross, radius, weight, keys, splittings, slices, last_element)
        
    else:
        print "stackfile " + stackfile + " already exists."
        print "Delete it or use different label to rerun this script."
        exit(0)


