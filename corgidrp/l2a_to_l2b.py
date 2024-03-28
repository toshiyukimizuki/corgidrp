# A file that holds the functions that transmogrify l2a data to l2b data 
import numpy as np

def dark_subtraction(input_dataset, dark_frame):
    """
    
    Perform dark current subtraction of a dataset using the corresponding dark frame

    Args:
        input_dataset (corgidrp.data.Dataset): a dataset of Images that need dark subtraction (L2a-level)
        dark_frame (corgidrp.data.Dark): a Dark frame to model the dark current

    Returns:
        corgidrp.data.Dataset: a dark subtracted version of the input dataset including error propagation
    """
    # you should make a copy the dataset to start
    darksub_dataset = input_dataset.copy()

    darksub_cube = darksub_dataset.all_data - dark_frame.data
    
    # propagate the error of the dark frame
    if hasattr(dark_frame, "err"):
        darksub_dataset.add_error_term(dark_frame.err, "dark_error")   
    else:
        raise Warning("no error attribute in the dark frame")
    
    #darksub_dataset.all_err = np.array([frame.err for frame in darksub_dataset.frames])
    history_msg = "Dark current subtracted using dark {0}".format(dark_frame.filename)

    # update the output dataset with this new dark subtracted data and update the history
    darksub_dataset.update_after_processing_step(history_msg, new_all_data=darksub_cube)

    return darksub_dataset

def frame_select(input_dataset):
    """
    
    Selects the frames that we want to use for further processing. 
    TODO: Decide on frame selection criteria

    Args:
        input_dataset (corgidrp.data.Dataset): a dataset of Images (L2a-level)

    Returns:
        corgidrp.data.Dataset: a version of the input dataset with only the frames we want to use
    """
    return None

def convert_to_electrons(input_dataset): 
    """
    
    Convert the data from ADU to electrons. 
    TODO: Establish the interaction with the CalDB for obtaining gain calibration 
    TODO: Make sure to update the headers to reflect the change in units

    Args:
        input_dataset (corgidrp.data.Dataset): a dataset of Images (L2a-level)

    Returns:
        corgidrp.data.Dataset: a version of the input dataset with the data in electrons
    """

    return None 

def em_gain_division(input_dataset):
    """
    
    Convert the data from electrons to photo-electrons by dividing the commanded em_gain. 
    update the change in units in the header [e/phot].

    Args:
        input_dataset (corgidrp.data.Dataset): a dataset of Images (L2a-level)

    Returns:
        corgidrp.data.Dataset: a version of the input dataset with the data in units photo-electrons
    """
    
    # you should make a copy the dataset to start
    emgain_dataset = input_dataset.copy()

    emgain = emgain_dataset[0].ext_hdr["CMDGAIN"]
    emgain_cube = emgain_dataset.all_data/emgain
    emgain_error = emgain_dataset.all_err/emgain
    
    history_msg = "data divided by em_gain {0}".format(str(emgain))

    # update the output dataset with this em_gain divided data and update the history
    emgain_dataset.update_after_processing_step(history_msg, new_all_data=emgain_cube, new_all_err=emgain_error, header_entries = {"BUNIT":"e/phot"})

    return emgain_dataset
    
    

def cti_correction(input_dataset):
    """
    
    Apply the CTI correction to the dataset.
    TODO: Establish the interaction with the CalDB for obtaining CTI correction calibrations

    Args:
        input_dataset (corgidrp.data.Dataset): a dataset of Images (L2a-level)
        
    Returns:
        corgidrp.data.Dataset: a version of the input dataset with the CTI correction applied
    """

    return None

def flat_division(input_dataset, master_flat):
    """
    
    Divide the dataset by the master flat field. 

    Args:
        input_dataset (corgidrp.data.Dataset): a dataset of Images (L2a-level)
        master_flat (corgidrp.data.Flat): a master flat field to divide by

    Returns:
        corgidrp.data.Dataset: a version of the input dataset with the flat field divided out
    """

    return None

def correct_bad_pixels(input_dataset):
    """
    
    Compute bad pixel map and correct for bad pixels. 

    MMB Notes: 
        - We'll likely want to be able to accept an external bad pixel map, either 
        from the CalDB or input by a user. 
        - We may want to accept just a list of bad pixels from a user too, thus 
        saving them the trouble of actually making their own map. 
        - We may want flags to decide which pixels in the DQ we correct. We may 
        not want to correct everything in the DQ extension
        - Different bad pixels in the DQ may be corrected differently.


    Args:
        input_dataset (corgidrp.data.Dataset): a dataset of Images (L2a-level)

    Returns:
        corgidrp.data.Dataset: a version of the input dataset with bad pixels corrected
    """

    return None

