#!/usr/bin/env python3
import numpy as np
import casacore.tables as pt
import os
import sys
import subprocess
import argparse

################################
##### Function definitions #####

def run_cmd(cmd: str):
    """Utility function to run shell commands safely."""
    print(f"\n[RUNNING] {cmd}\n")
    # subprocess.run with check=True will automatically stop the script if the bash command fails
    subprocess.run(cmd, shell=True, check=True)

def model_inject(ms_path: str, stepsize: int = 10000):
    """
    Injects MODEL_DATA into the noise column (CORRECTED_DATA or DATA).
    Now takes the explicit path to the MS as an argument.
    """
    outcolumn = "MODEL_INJECTED_DATA"
    
    if not os.path.exists(ms_path):
        raise FileNotFoundError(f"Measurement set not found: {ms_path}")

    ts = pt.table(ms_path, readonly=False)
    colnames = ts.colnames()
    
    # Determine which noise column is available
    noise_col = 'CORRECTED_DATA' if 'CORRECTED_DATA' in colnames else 'DATA'
    
    for row in range(0, ts.nrows(), stepsize):
        print(f"Injection: Doing {row} out of {ts.nrows()}, (step: {stepsize})")
        print(f'Reading {noise_col} column')
        data = ts.getcol(noise_col, startrow=row, nrow=stepsize, rowincr=1)
        
        print('Reading MODEL column')
        model = ts.getcol('MODEL_DATA', startrow=row, nrow=stepsize, rowincr=1)
        
        print('Injecting...')
        ts.putcol(outcolumn, data + model, startrow=row, nrow=stepsize, rowincr=1)
        
    ts.close()
    print("Model injection complete!")


###############################
######### Main script #########

def main():
    parser = argparse.ArgumentParser(description="LOFAR simulation pipeline: synthms -> losito -> DP3 -> wsclean")
    
    # Required arguments
    parser.add_argument('--name', type=str, required=True, help="Base name for the measurement set (e.g., mockMS_LBA_8H)")
    parser.add_argument('--model', type=str, required=True, help="Path to the FITS model image prefix for wsclean predict (no .fits extension)")
    
    # Optional arguments with defaults based on your original script
    parser.add_argument('--ra', type=float, default=123.6125, help="Right Ascension in degrees")
    parser.add_argument('--dec', type=float, default=52.9157, help="Declination in degrees")
    parser.add_argument('--mjd', type=float, default=59900, help="Start MJD")
    parser.add_argument('--tobs', type=float, default=8.0, help="Observation time in hours")
    parser.add_argument('--minfreq', type=float, default=30, help="Minimum frequency in MHz")
    parser.add_argument('--maxfreq', type=float, default=74, help="Maximum frequency in MHz")
    parser.add_argument('--chanpersb', type=int, default=4, help="Channels per subband")
    parser.add_argument('--tres', type=int, default=4, help="Time resolution in seconds")
    parser.add_argument('--lofarver', type=int, default=2, help="LOFAR version (1 or 2)")
    parser.add_argument('--station', type=str, default='LBA', choices=['LBA', 'HBA'], help="Station type")
    
    args = parser.parse_args()

    # Convert RA/DEC to radians as expected by synthms (based on your original code)
    ra_rad = np.radians(args.ra)
    dec_rad = np.radians(args.dec)
    mjd_sec = args.mjd * 86400

    merged_ms = f"{args.name}_merged.MS"

    ##### 1. Create empty MS
    run_cmd(f"synthms --name {args.name} --start {mjd_sec} --tobs {args.tobs} --ra {ra_rad} --dec {dec_rad} --station {args.station} --lofarversion {args.lofarver} --minfreq {args.minfreq*1e6} --maxfreq {args.maxfreq*1e6} --chanpersb {args.chanpersb} --tres {args.tres}")
    print("MS creation complete!")

    ##### 1.1 Dynamically generate model.sky file
    print("\n[GENERATING] model.sky...")
    # Using textwrap.dedent implicitly via standard string formatting to avoid weird indentations
    sky_content = f"""format = Name, Type, Patch, Ra, Dec, I, Q, U, V, MajorAxis, MinorAxis, Orientation, ReferenceFrequency, SpectralIndex, LogarithmicSI
     , , patch_s1, 08:13:36.000, +48.13.3.000
    s1, POINT, patch_s1, 08:13:36.000, +48.13.3.000, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 48826599.12109375, [-0.5], true
     , , patch_s2, 08:13:36.000, +48.43.3.000
    s2, POINT, patch_s2, 08:13:36.000, +48.43.3.000, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 48826599.12109375, [-0.5], true
     , , patch_s3, 08:16:36.099, +48.13.3.000
    s3, POINT, patch_s3, 08:16:36.099, +48.13.3.000, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 48826599.12109375, [-0.5], true
     , , patch_s4, 08:13:36.000, +47.43.3.000
    s4, POINT, patch_s4, 08:13:36.000, +47.43.3.000, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 48826599.12109375, [-0.5], true
     , , patch_s5, 08:10:35.902, +48.13.3.000
    s5, POINT, patch_s5, 08:10:35.902, +48.13.3.000, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 48826599.12109375, [-0.5], true
    """
    with open("model.sky", "w") as f:
        f.write(sky_content)
    print("Generated model.sky file!")

    ##### 1.2 Dynamically generate noise.parset
    print("\n[GENERATING] noise.parset...")
    # Using textwrap.dedent implicitly via standard string formatting to avoid weird indentations
    parset_content = f"""# LoSiTo parset
    msin = {args.name}_t*.MS
    skymodel = model.sky

    # Add noise to predicted visibilities
    [noise]
    operation = NOISE
    outputColumn = DATA
    """
    with open("noise.parset", "w") as f:
        f.write(parset_content)
    print("Generated noise.parset file!")

    ##### 2. Inject noise (Assumes noise.parset is in the current working directory)
    run_cmd("losito noise.parset")
    print("Noise complete!")

    ##### 3. Merge MS chunks and apply dysco compression
    run_cmd(f"DP3 msin={args.name}_t*.MS msout={merged_ms} steps=[] msout.storagemanager=dysco")
    print("DP3 merge complete!")

    ##### 4. Duplicate DATA column to MODEL_INJECTED_DATA
    run_cmd(f"DP3 msin={merged_ms} msout=. steps=[] msin.datacolumn=DATA msout.datacolumn=MODEL_INJECTED_DATA")
    print("DP3 MODEL_INJECTED_DATA complete")

    ##### 5. Predict visibilities from model FITS
    run_cmd(f"wsclean -predict -name {args.model} -channels-out 16 {merged_ms}")
    print("Predict complete!")

    ##### 6. Inject the model into the noise
    model_inject(merged_ms)

    ##### 7. Final Imaging
    # Constructing a dynamic output name based on your input name
    out_image_name = f"Obs_{args.name}_taper30" 
    
    run_cmd(f"wsclean -j 128 -name {out_image_name} -data-column MODEL_INJECTED_DATA -size 10000 10000 -padding 1.2 -scale 5arcsec -weight briggs -0.5 -gridder wgridder -niter 1000000 -nmiter 20 -mgain 0.8 -multiscale-scale-bias 0.6 -minuv-l 30 -join-channels -channels-out 16 -multiscale -no-update-model-required -auto-threshold 2.0 -auto-mask 3.0 -parallel-gridding 32 -taper-gaussian 30 {merged_ms}/")
    print("Final imaging complete!")

if __name__ == "__main__":
    main()
