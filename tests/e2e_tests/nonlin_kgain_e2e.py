""" Module to test the generation of both nonlin and kgain from the same PUPILIMG dataset """
import os
import glob
import argparse
import pytest
import numpy as np
from astropy import time
from astropy.io import fits
import matplotlib.pyplot as plt

import corgidrp
from corgidrp import data
from corgidrp import mocks
from corgidrp import walker
from corgidrp import caldb

thisfile_dir = os.path.dirname(__file__)  # this file's folder

def set_vistype_for_tvac(
    list_of_fits,
    ):
    """ Adds proper values to VISTYPE for non-linearity calibration.

    This function is unnecessary with future data because data will have
    the proper values in VISTYPE. Hence, the "tvac" string in its name.
    For reference, TVAC data used to calibrate non-linearity were the
    following 382 files with IDs: 51841-51870 (30: mean frame). And NL:
    51731-51840 (110), 51941-51984 (44), 51986-52051 (66), 55122-55187 (66),
    55191-55256 (66)  

    Args:
    list_of_fits (list): list of FITS files that need to be updated.
    """
    print("Adding VISTYPE='PUPILIMG' to TVAC data")
    for file in list_of_fits:
        fits_file = fits.open(file)
        prihdr = fits_file[0].header
        # Adjust VISTYPE
        prihdr['VISTYPE'] = 'PUPILIMG'
        # Update FITS file
        fits_file.writeto(file, overwrite=True)


@pytest.mark.e2e
def test_nonlin_and_kgain_e2e(
    tvacdata_path,
    e2eoutput_path,
    ):
    """ 
    Performs the e2e test to generate both nonlin and kgain calibrations from the same
    L1 pupilimg dataset

    Args:
        tvacdata_path (str): Location of L1 data. Folders for both kgain and nonlin
        e2eoutput_path (str): Location of the output products: recipes, non-linearity
            calibration FITS file, and kgain fits file

    """

    # figure out paths, assuming everything is located in the same relative location
    nonlin_l1_datadir = os.path.join(tvacdata_path,
        'TV-20_EXCAM_noise_characterization', 'nonlin')
    kgain_l1_datadir = os.path.join(tvacdata_path,
        'TV-20_EXCAM_noise_characterization', 'kgain')

    e2eoutput_path = os.path.join(e2eoutput_path, 'nonlin_and_kgain_output')

    if not os.path.exists(nonlin_l1_datadir):
        raise FileNotFoundError('Please store L1 data used to calibrate non-linearity',
            f'in {nonlin_l1_datadir}')
    if not os.path.exists(kgain_l1_datadir):
        raise FileNotFoundError('Please store L1 data used to calibrate kgain',
            f'in {kgain_l1_datadir}')

    if not os.path.exists(e2eoutput_path):
        os.mkdir(e2eoutput_path)

    # Define the raw science data to process
    nonlin_l1_list = glob.glob(os.path.join(nonlin_l1_datadir, "*.fits"))
    nonlin_l1_list.sort()
    kgain_l1_list = glob.glob(os.path.join(kgain_l1_datadir, "*.fits"))
    kgain_l1_list.sort()
    pupilimg_l1_list = nonlin_l1_list + kgain_l1_list

    # Set TVAC OBSTYPE to MNFRAME/NONLIN (flight data should have these values)
    set_vistype_for_tvac(pupilimg_l1_list)

   
    # Run the walker on some test_data
    print('Running walker')
    walker.walk_corgidrp(pupilimg_l1_list, '', e2eoutput_path)

    # check that files can be loaded from disk successfully. no need to check correctness as done in other e2e tests
    # NL from CORGIDRP
    possible_nonlin_files = glob.glob(os.path.join(e2eoutput_path, '*_NonLinearityCalibration.fits'))
    nonlin_drp_filepath = max(possible_nonlin_files, key=os.path.getmtime) # get the one most recently modified
    nonlin = data.NonLinearityCalibration(nonlin_drp_filepath)

    # kgain from corgidrp
    possible_kgain_files = glob.glob(os.path.join(e2eoutput_path, '*_kgain.fits'))
    kgain_filepath = max(possible_kgain_files, key=os.path.getmtime) # get the one most recently modified
    kgain = data.Kgain(kgain_filepath)

    # remove entry from caldb
    this_caldb = caldb.CalDB()
    this_caldb.remove_entry(nonlin)
    this_caldb.remove_entry(kgain)

   # Print success message
    print('e2e test for NL passed')

if __name__ == "__main__":

    # Use arguments to run the test. Users can then write their own scripts
    # that call this script with the correct arguments and they do not need
    # to edit the file. The arguments use the variables in this file as their
    # defaults allowing the use to edit the file if that is their preferred
    # workflow.

    TVACDATA_DIR = '/home/jwang/Desktop/CGI_TVAC_Data/'
    OUTPUT_DIR = thisfile_dir

    ap = argparse.ArgumentParser(description="run the non-linearity end-to-end test")
    ap.add_argument("-tvac", "--tvacdata_dir", default=TVACDATA_DIR,
                    help="Path to CGI_TVAC_Data Folder [%(default)s]")
    ap.add_argument("-o", "--output_dir", default=OUTPUT_DIR,
                    help="directory to write results to [%(default)s]")
    args = ap.parse_args()
    # Run the e2e test
    test_nonlin_and_kgain_e2e(args.tvacdata_dir, args.output_dir)
