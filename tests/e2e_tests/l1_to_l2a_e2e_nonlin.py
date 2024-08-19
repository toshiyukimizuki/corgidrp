import argparse
import glob
import numpy as np
import os
import astropy.time as time
import corgidrp
import corgidrp.data as data
import corgidrp.mocks as mocks
import corgidrp.walker as walker

corgidrp_dir = os.path.join(os.path.dirname(corgidrp.__file__), '..') # basedir of entire corgidrp github repo

nonlin_tvac = os.path.join(corgidrp_dir, '../e2e_tests_corgidrp/nonlin_table_240322.txt')
nonlin_l1_datadir = os.path.join(corgidrp_dir, '../e2e_tests_corgidrp/')
outputdir = './l1_to_l2a_output/'

def main():
    if not os.path.exists(outputdir):
        os.mkdir(outputdir)

    # Define the raw science data to process
    nonlin_l1_dat = glob.glob(os.path.join(nonlin_l1_datadir, "*.fits"))
    nonlin_l1_dat.sort()

    # Non-linearity calibration file used to compare the output from CORGIDRP:
    # We are going to make a new nonlinear calibration file using
    # a combination of the II&T nonlinearty file and the mock headers from
    # our unit test version of the NonLinearityCalibration
    nonlin_dat = np.genfromtxt(nonlin_tvac, delimiter=",")
    pri_hdr, ext_hdr = mocks.create_default_headers()
    ext_hdr["DRPCTIME"] = time.Time.now().isot
    ext_hdr['DRPVERSN'] =  corgidrp.__version__
    mock_input_dataset = data.Dataset(nonlin_l1_dat)
    nonlinear_cal = data.NonLinearityCalibration(nonlin_dat,
                                                 pri_hdr=pri_hdr,
                                                 ext_hdr=ext_hdr,
                                                 input_dataset=mock_input_dataset)
    nonlinear_cal.save(filedir=outputdir, filename="mock_nonlinearcal.fits" )

    # Run the walker on some test_data
    walker.walk_corgidrp(l1_data_filelist, '', outputdir)

    breakpoint()
    # Compare results

if __name__ == "__main__":
    # Use arguments to run the test. Users can then write their own scripts
    # that call this script with the correct arguments and they do not need
    # to edit the file. The arguments use the variables in this file as their
    # defaults allowing the use to edit the file if that is their preferred
    # workflow.
    ap = argparse.ArgumentParser(description="run the l1->l2a end-to-end test")
    ap.add_argument("-np", "--nonlin_tvac", default=nonlin_tvac,
                    help="text file containing the non-linear table from TVAC [%(default)s]")
    ap.add_argument("-l1", "--nonlin_l1_datadir", default=nonlin_l1_datadir,
                    help="directory that contains the L1 data files used for nonlinearity calibration [%(default)s]")
    ap.add_argument("-o", "--outputdir", default=outputdir,
                    help="directory to write results and it will be created if it does not exist [%(default)s]")
    args = ap.parse_args()
    nonlin_path = args.nonlin_tvac
    l1_datadir = args.nonlin_l1_datadir
    outputdir = args.outputdir
    main()
