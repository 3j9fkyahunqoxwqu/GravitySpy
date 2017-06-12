#!/usr/bin/env python

import optparse,os,string,random,pdb,socket
from gwpy.table.lsctables import SnglBurstTable
from gwpy.segments import DataQualityFlag
import pandas as pd
from sqlalchemy.engine import create_engine

###############################################################################
##########################                             ########################
##########################   Func: parse_commandline   ########################
##########################                             ########################
###############################################################################
# Definite Command line arguments here

def parse_commandline():
    """
    Parse the options given on the command-line.
    """
    parser = optparse.OptionParser()
    parser.add_option("--applyallDQ", action="store_true", default=False,help="Generate a list of omicron triggers that exclude all of the DQ cuts already created by detchar. (Default:False)")
    parser.add_option("--channelname", help="channel name [Default:GDS-CALIB_STRAIN]",
                        default="GDS-CALIB_STRAIN")
    parser.add_option("--detector", help="detector name [L1 or H1]. [No Default must supply]")
    parser.add_option("--durHigh", help="The max duration of a glitch you want to make images for [Optional Input]",type=float)
    parser.add_option("--durLow", help="lower duration of a glitch you want to make images for[Optional Input]",type=float)
    parser.add_option("--gpsStart", type=int,help="gps Start Time of Query for meta data and omega scans. If not supplied will attempt to imply from datatable",default=0)
    parser.add_option("--gpsEnd", type=int,help="gps End Time If not supplied will attempt to imply from datatable",default=0)
    parser.add_option("--freqHigh", help="upper frequency bound cut off for the glitches. [Default: 2048]",type=int,default=2048)
    parser.add_option("--freqLow", help="lower frequency bound cut off for the glitches. [Default: 10]",type=int,default=10)
    parser.add_option("--maxSNR", help="This flag gives you the option to supply a upper limit to the SNR of the glitches [Optional Input]",type=float)
    parser.add_option("--outDir", help="Outdir of omega scan and omega scan webpage (i.e. your html directory)")
    parser.add_option("--pathToExec", help="Path to version of wscan.py you want to use")
    parser.add_option("--pathToExecUpload", help="Path to version of wscan.py you want to use")
    parser.add_option("--pathToIni", help="Path to ini file")
    parser.add_option("--pathToModel",default='./ML/trained_model/' ,help="Path to trained model")
    parser.add_option("--SNR", help="Lower bound SNR Threshold for omicron triggers, by default there is no upperbound SNR unless supplied throught the --maxSNR flag. [Default: 6]",type=float,default=6)
    parser.add_option("--uniqueID", action="store_true", default=False,help="Is this image being generated for the GravitySpy project, is so we will create a uniqueID strong to use for labeling images instead of GPS time")
    parser.add_option("--HDF5", action="store_true", default=False,help="Store triggers in local HDF5 table format")
    parser.add_option("--PostgreSQL", action="store_true", default=False,help="Store triggers in local PostgreSQL format")
    parser.add_option("--upload", action="store_true", default=False,help="You plan on uploading to the gravityspywebsite")

    opts, args = parser.parse_args()

    return opts

###############################################################################
##########################                             ########################
##########################   Func: id_generator        ########################
##########################                             ########################
###############################################################################

def id_generator(x,size=10, chars=string.ascii_uppercase + string.digits +string.ascii_lowercase):
    return ''.join(random.SystemRandom().choice(chars) for _ in range(size))

###############################################################################
##########################                              #######################
##########################   Func: threshold            #######################
##########################                              #######################
###############################################################################
# Define threshold function that will filter omicron triggers based on SNR and frequency threshold the user sets (or the defaults.)

def threshold(row):
    passthresh = True
    if not opts.durHigh is None:
	passthresh = ((row.duration <= opts.durHigh) and passthresh)
    if not opts.durLow is None:
        passthresh = ((row.duration >= opts.durLow) and passthresh)
    if not opts.freqHigh is None:
        passthresh = ((row.peak_frequency <= opts.freqHigh) and passthresh)
    if not opts.freqLow is None:
        passthresh = ((row.peak_frequency >= opts.freqLow) and passthresh)
    if not opts.maxSNR is None:
        passthresh = ((row.snr <= opts.maxSNR) and passthresh)
    if not opts.SNR is None:
        passthresh = ((row.snr >= opts.SNR) and passthresh)
    return passthresh


###############################################################################
##########################                          ###########################
##########################   Func: get_triggers     ###########################
##########################                          ###########################
###############################################################################

# This function queries omicron to obtain trigger times of the glitches. It then proceeds to filter out these times based on whether the detector was in an analysis ready state or the glitch passes certain frequency and SNR cuts. 

def get_triggers(gpsStart,gpsEnd,detector):

    # Obtain segments that are analysis ready
    analysis_ready = DataQualityFlag.query('{0}:DMT-ANALYSIS_READY:1'.format(detector),float(gpsStart),float(gpsEnd))

    # Display segments for which this flag is true
    print "Segments for which the ANALYSIS READY Flag is active: {0}".format(analysis_ready.active)

    omicrontriggers = SnglBurstTable.fetch(detchannelname,'Omicron',\
    float(gpsStart),float(gpsEnd),filt=threshold)

    print "List of available metadata information for a given glitch provided by omicron: {0}".format(omicrontriggers.columnnames)

    print "Number of triggers after SNR and Freq cuts but before ANALYSIS READY flag filtering: {0}".format(len(omicrontriggers))

    # Filter the raw omicron triggers against the ANALYSIS READY flag.
    omicrontriggers = omicrontriggers.vetoed(analysis_ready.active)

    print "Final trigger length: {0}".format(len(omicrontriggers))

    return omicrontriggers

###############################################################################
##########################                            #########################
##########################   Func: write_dagfile     #########################
##########################                            #########################
###############################################################################

# Write dag_file file for the condor job

def write_dagfile(x):
    with open('gravityspy_{0}_{1}.dag'.format(oTriggers.peak_time.min(),oTriggers.peak_time.max()),'a+') as dagfile:
        dagfile.write('JOB {0}{1}{2} ./condor/gravityspy.sub\n'.format(x.peak_time,x.peak_time_ns,x.event_id))
        dagfile.write('RETRY {0}{1}{2} 10\n'.format(x.peak_time,x.peak_time_ns,x.event_id))
        dagfile.write('VARS {0}{1}{4} jobNumber="{0}{1}{4}" eventTime="{2}" ID="{3}"'.format(x.peak_time,x.peak_time_ns,x.peakGPS,x.uniqueID,x.event_id))
        if opts.upload:
            listOfParentJobs.append('{0}{1}{2}'.format(x.peak_time,x.peak_time_ns,x.event_id))
        dagfile.write('\n\n')

###############################################################################
##########################                                #####################
##########################   Func: write_dagfile_upload   #####################
##########################                                #####################
###############################################################################

# Write dag_file file for the condor job

def write_dagfile_upload():
    with open('gravityspy_{0}_{1}.dag'.format(oTriggers.peak_time.min(),oTriggers.peak_time.max()),'a+') as dagfile:
        iT=0
        listOfChildJobs = []
        for iLabel in ["1080Lines","1400Ripples","Air_Compressor","Blip","Chirp","Extremely_Loud","Helix","Koi_Fish","Light_Modulation","Low_Frequency_Burst","Low_Frequency_Lines","No_Glitch","None_of_the_Above","Paired_Doves","Power_Line","Repeating_Blips","Scattered_Light","Scratchy","Tomte","Violin_Mode","Wandering_Line","Whistle"]:
            iT= iT +1
            dagfile.write('JOB {0} ./condor/upload.sub\n'.format(iT))
            dagfile.write('VARS {0} jobNumber="{0}" Label="{1}"\n'.format(iT,iLabel))
            listOfChildJobs.append(str(iT))
            dagfile.write('\n\n')
        dagfile.write('PARENT {0} CHILD {1}'.format(' '.join(listOfParentJobs),' '.join(listOfChildJobs)))


###############################################################################
##########################                            #########################
##########################   Func: write_subfile     #########################
##########################                            #########################
###############################################################################

# Write submission file for the condor job

def write_subfile():
    for d in ['logs', 'condor']:
        if not os.path.isdir(d):
            os.makedirs(d)
    with open('./condor/gravityspy.sub', 'w') as subfile:
        subfile.write('universe = vanilla\n')
        subfile.write('executable = {0}\n'.format(opts.pathToExec))
        subfile.write('\n')
        if opts.PostgreSQL:
            subfile.write('arguments = "--inifile {0} --eventTime $(eventTime) --outDir {1} --pathToModel {2} --uniqueID --ID $(ID) --runML --PostgreSQL"\n'.format(opts.pathToIni,opts.outDir,opts.pathToModel))
        elif opts.HDF5:
            subfile.write('arguments = "--inifile {0} --eventTime $(eventTime) --outDir {1} --pathToModel {2} --uniqueID --ID $(ID) --runML --HDF5"\n'.format(opts.pathToIni,opts.outDir,opts.pathToModel))
        subfile.write('getEnv=True\n')
        subfile.write('\n')
        subfile.write('accounting_group_user = scott.coughlin\n')#.format(opts.username))
        subfile.write('accounting_group = ligo.dev.o1.detchar.ch_categorization.glitchzoo\n')
        subfile.write('\n')
        subfile.write('priority = 0\n')
        subfile.write('request_memory = 1000\n')
        subfile.write('\n')
        subfile.write('error = logs/gravityspy-$(jobNumber).err\n')
        subfile.write('output = logs/gravityspy-$(jobNumber).out\n')
        subfile.write('notification = never\n')
        subfile.write('queue 1')
        subfile.close()

###############################################################################
##########################                            #########################
##########################   Func: write_subfile     #########################
##########################                            #########################
###############################################################################

# Write submission file for the condor job

def write_subfile_upload(detector):
    for d in ['logs_upload', 'condor']:
        if not os.path.isdir(d):
            os.makedirs(d)
    with open('./condor/upload.sub', 'w') as subfile:
        subfile.write('universe = local\n')
        subfile.write('executable = {0}\n'.format(opts.pathToExecUpload))
        subfile.write('\n')
        subfile.write('arguments = "--Label $(Label) --detector {0}"\n'.format(detector))
        subfile.write('getEnv=True\n')
        subfile.write('\n')
        subfile.write('accounting_group_user = scott.coughlin\n')#.format(opts.username))
        subfile.write('accounting_group = ligo.dev.o1.detchar.ch_categorization.glitchzoo\n')
        subfile.write('\n')
        subfile.write('priority = 0\n')
        subfile.write('request_memory = 1000\n')
        subfile.write('\n')
        subfile.write('error = logs_upload/gravityspy-$(jobNumber).err\n')
        subfile.write('output = logs_upload/gravityspy-$(jobNumber).out\n')
        subfile.write('notification = never\n')
        subfile.write('queue 1')
        subfile.close()

############################################################################
###############          MAIN        #######################################
############################################################################

# Parse commandline arguments
opts = parse_commandline()

# attempt to determine detector based on cluster currently running on
fullhostname = socket.getfqdn()
if 'wa' in fullhostname:
    detector = 'H1'
elif 'la' in fullhostname
    detector = 'L1'
else:
    detector = opts.detector

if opts.HDF5:
    # Determine start and stop time of trigger query.
    if not opts.gpsStart:
        tmp = pd.read_hdf('triggers.h5')
        gpsStart = tmp.peak_time.max()
    else:
        gpsStart = opts.gpsStart

    if not opts.gpsEnd:
        gpsEnd = gpsStart + 28800
    else:
        gpsEnd = opts.gpsEnd

    # Take the detector and the channel from the command line and combine them into one string. This is needed for some input later on.
    detchannelname = detector + ':' + opts.channelname

    write_subfile()
    omicrontriggers = get_triggers(gpsStart,gpsEnd,detector)
    oTriggers = pd.DataFrame(omicrontriggers.to_recarray(),omicrontriggers.get_peak()).reset_index()
    oTriggers.rename(columns = {'index':'peakGPS'},inplace=True)
    oTriggers['uniqueID'] = oTriggers.peakGPS.apply(id_generator)
    oTriggers[['peak_time','peak_time_ns','peakGPS','uniqueID','event_id']].apply(write_dagfile,axis=1)
    oTriggers.peakGPS = oTriggers.peakGPS.apply(float)
    oTriggers.to_hdf('triggers.h5','gspy_triggers',append=True)

elif opts.PostgreSQL:

    engine = create_engine('postgresql://{0}:{1}@gravityspy.ciera.northwestern.edu:5432/gravityspy'.format(os.environ['QUEST_SQL_USER'],os.environ['QUEST_SQL_PASSWORD']))

    if not opts.gpsStart:
        tmp = pd.read_sql('glitches',engine)
        gpsStart = tmp.loc[tmp.ifo == detector,'peak_time'].max()
    else:
        gpsStart = opts.gpsStart

    if not opts.gpsEnd:
        gpsEnd = gpsStart + 604800
    else:
        gpsEnd = opts.gpsEnd

    # Take the detector and the channel from the command line and combine them into one string. This is needed for some input later on.
    detchannelname = detector + ':' + opts.channelname

    write_subfile()
    if opts.upload:
        write_subfile_upload(detector)
        listOfParentJobs = []
    omicrontriggers = get_triggers(gpsStart,gpsEnd,detector)

    oTriggers = pd.DataFrame(omicrontriggers.to_recarray(),omicrontriggers.get_peak()).reset_index()
    oTriggers.sort_values('peak_time',ascending=False,inplace=True)
    oTriggers.rename(columns = {'index':'peakGPS'},inplace=True)
    oTriggers['uniqueID'] = oTriggers.peakGPS.apply(id_generator)
    oTriggers[['peak_time','peak_time_ns','peakGPS','uniqueID','event_id']].apply(write_dagfile,axis=1)
    if opts.upload:
        write_dagfile_upload()
    oTriggers.peakGPS = oTriggers.peakGPS.apply(float)
    oTriggers.to_sql('glitches',engine,index=False,if_exists='append')
    os.system('/bin/condor_submit_dag gravityspy_{0}_{1}.dag'.format(oTriggers.peak_time.min(),oTriggers.peak_time.max())) 
