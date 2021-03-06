#!/bin/env python

import os, errno, json
import matplotlib
matplotlib.use('agg')
import pylab as plt
import numpy as np
from sys import argv
from shear_stacking import *

def makeSlicedProfile(ax, key_name, profile, plot_type, limits, lw=1):
    if config['coords'] == "angular":
        ax.plot(xlim, [0,0], 'k:')
    if plt.matplotlib.rcParams['text.usetex']:
        title = r'\texttt{' + key_name.replace("_", "\_") + '}'
    else:
        title = key_name

    # make the profile for all
    if plot_type == "shear" or plot_type == "scalar":
        ax.errorbar(profile['all']['mean_r'], profile['all']['mean_q'], yerr=profile['all']['std_q'], c='k', marker='.', label='all', lw=lw)
    else:
        ax.errorbar(profile['all']['mean_r'], profile['all']['sum_w'], yerr=None, c='k', marker='.', label='all', lw=lw)

    # make the profile for each split
    colors = getColors(len(limits))
    for s in range(len(limits)-1):
        pname = key_name + "_%d" % s
        label = '$\in ['
        if isinstance(limits[s], (int, long)):
            label += '%d, ' % limits[s]
        else:
            label += '%.2f, ' % limits[s]
        if isinstance(limits[s+1], (int, long)):
            label += '%d)$' % limits[s+1]
        else:
            label += '%.2f)$' % limits[s+1]
        if plot_type == "shear" or plot_type == "scalar":
            ax.errorbar(profile[pname]['mean_r'], profile[pname]['mean_q'], yerr=profile[pname]['std_q'], c=colors[s], marker='.', label=label, lw=lw)
        else:
            ax.errorbar(profile[pname]['mean_r'], profile[pname]['sum_w'], yerr=None, c=colors[s], marker='.', label=label, lw=lw)

    # xlimits
    xmin = profile['all']['mean_r'].min() / 2
    xmax = profile['all']['mean_r'].max() * 2
    ax.set_xlim(xmin, xmax)

    # avoid negative values in shear plots
    if plot_type == "shear":
        ymin, ymax = (1e3, 1e7)
        #ymin, ymax = -0.1, 0.1
        ax.set_ylim(ymin, ymax)
    
    # decorations
    n_pair = profile['all']['n'].sum()
    label = getOrderOfMagnitudeLabel(n_pair, digits=2)
    ax.text(0.05, 0.95, r'$n_\mathrm{pair} = %s$' % (label), ha='left', va='top', transform=ax.transAxes, fontsize='small')
    legend = ax.legend(loc='upper right', numpoints=1, title=title, frameon=False, fontsize='small')
    plt.setp(legend.get_title(),fontsize='small')
    makeAxisLabels(ax, plot_type, config)

if __name__ == '__main__':
    # parse inputs
    try:
        configfile = argv[1]
        plot_type = argv[2]
    except IndexError:
        print "usage: " + argv[0] + " <config file> <shear/boost/scalar>"
        raise SystemExit
    try:
        fp = open(configfile)
        print "opening configfile " + configfile
        config = json.load(fp)
        fp.close()
    except IOError:
        print "configfile " + configfile + " does not exist!"
        raise SystemExit
    
    if plot_type not in ['shear', 'boost', 'scalar']:
        print "specify plot_type from ['shear', 'boost', 'scalar']"
        raise SystemExit
    
    indir = os.path.dirname(configfile) + "/"
    outdir = indir

    # load profiles
    file_name = "shear_"
    plot_name = file_name
    if plot_type == "boost":
        plot_name = "boost_"
    if plot_type == "scalar":
        file_name = "scalar_" + config['shape_scalar_key'] + "_"
        plot_name = file_name

    pnames = ['all']
    for key, limit in config['splittings'].iteritems():
        for s in xrange(len(limit)-1):
            pnames.append("%s_%d" % (key, s))
    profiles = {}
    for pname in pnames:
        profiles[pname] = np.load(outdir + file_name + pname + ".npz")
        
    # plot generation
    setTeXPlot(sampling=2)
    
    # new plot for each slice
    for key in config['splittings'].keys():
        print "  " + key
        fig = plt.figure(figsize=(5, 4))
        ax = fig.add_subplot(111)
        makeSlicedProfile(ax, key, profiles, plot_type, config)
        fig.subplots_adjust(wspace=0, hspace=0, left=0.16, bottom=0.15, right=0.98, top=0.95)
        plotfile = outdir + plot_name + "%s.png" % key
        print "saving " + plotfile
        fig.savefig(plotfile)

