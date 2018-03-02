#from panoptes_client import *

import pandas as pd
import numpy as np
import os, sys
import pickle
import pdb
import argparse

import params

### Argument handling ###

argp = argparse.ArgumentParser()
argp.add_argument("-f", "--file-name", default='', type=str, help="File stem for output data")
argp.add_argument("-nc", "--num-cores", default=None, type=int, help="Specify the number of cores that the retirement code will be parallelized over")
argp.add_argument("-i", "--index", default=None, type=int, help="Index which indicates the chunk of image files that retirement will be calculated for")

argp.add_argument("--min-label", default=2, type=int, help="Minimum number of citizen labels that an image must receive before it is retired. Default=2")
argp.add_argument("--max-label", default=50, type=int, help="Maximum number of citizen labels that an image must receive before it is retired as NOA. Default=50")
argp.add_argument("--ret-thresh", default=0.9, help="Retirement threshold that must be achieved to retire a particular class. Can be a float, or a 22-length vector of floats. Default = 0.9")
argp.add_argument("--prior", default='uniform', type=str, help="String indicating the prior choice for the subjects. Calls function from class params.py. Default=uniform")
argp.add_argument("--weighting", default='default', type=str, help="String indicating the weighting choice for the subjects. Calls function from class params.py. Default=default")
args = argp.parse_args()

if args.num_cores and args.index:
    multiproc=True
else:
    multiproc=False

# Obtain number of classes from API
with open("../data/workflowDictSubjectSets.pkl","rb") as f:
    workflowDictSubjectSets = pickle.load(f)
classes = sorted(workflowDictSubjectSets[2117].keys())

# From ansers Dict determine number of classes
numClasses = len(classes)

# Flat retirement criteria #FIXME make this work for vector of thresholds
ret_thresh = float(args.ret_thresh)*np.ones(numClasses)

# Flat priors b/c we do not know what category the image is in #FIXME make this work for other defined priors
priors = params.Priors()
if args.prior == 'uniform':
    prior = priors.uniform(numClasses)

# Load info about classifications and glitches
print '\nreading classifications...'
classifications = pd.read_pickle('../data/classifications.pkl')
classifications = classifications.loc[~(classifications.annotations_value_choiceINT == -1)]
# NOTE: we remove all classifications that were done on defunct workflows
classifications = classifications.loc[~(classifications.weight == 0.0)]

print 'reading glitches...'
glitches = pd.read_pickle('../data/glitches.pkl')
# filter glitches for only testing images
glitches = glitches.loc[glitches.ImageStatus != 'Training']
glitches['MLScore'] = glitches[classes].max(1)
glitches['MLLabel'] = glitches[classes].idxmax(1)

# Load confusion matrices
print 'reading confusion matrices...'
# call this combined data for memory purposes
combined_data = pd.read_pickle('../data/conf_matrices.pkl')

# Merge DBs
print 'combining data...'
combined_data = classifications.merge(combined_data, on=['id','links_user'])
combined_data = combined_data.merge(glitches, on=['links_subjects', 'uniqueID'])

# Remove unnecessary columns from combined_data
col_list = ['id','uniqueID','links_subjects','links_user','MLScore','MLLabel','annotations_value_choiceINT','conf_matrix','weight','metadata_finished_at']+sorted(workflowDictSubjectSets[2117].keys())
combined_data = combined_data[col_list]

#Must start with earlier classifications and work way to new ones
combined_data.drop_duplicates(['links_subjects','links_user'],inplace=True)

# Create imageDB
columnsForImageDB = sorted(workflowDictSubjectSets[2117].keys())
columnsForImageDB.extend(['uniqueID','links_subjects','MLScore','MLLabel','id'])
image_db = combined_data[columnsForImageDB].drop_duplicates(['links_subjects'])
image_db.set_index(['links_subjects'],inplace=True)
image_db['numLabel'] = 0
image_db['retired'] = 0
image_db['numClassifications'] = 0
image_db['finalScore'] = 0.0
image_db['finalLabel'] = ''
image_db['cum_weight'] = 0.0


def get_post_contribution(x):
    # NOTE: the subject link is the variable x
    # find all classifications for a particular subject
    glitch = combined_data[combined_data.links_subjects==x]
    # NOTE: for now only take classifications from registered users
    glitch = glitch[glitch.links_user != 0]
    # ensure each classification id has a confusion matrix
    matrices = combined_data[combined_data.id.isin(glitch.id)]
    glitch = glitch[glitch.id.isin(matrices.id)]
    # sort based on when the classification was made
    glitch = glitch.sort_values('metadata_finished_at')
    # counter to keep track of the weighting normalization, starts at 1.0 for machine
    weight_ctr = 1.0
    # track the contribution of each user towards retirement (can take first entry for intial ML score)
    tracker = np.atleast_2d(glitch.iloc[0][classes].values)

    # loop through all people that classified until retirement is reached
    for idx, person in enumerate(glitch.links_user):
        # for now, let's assume everything with >50 classifications and no retirement has not retired
        if image_db.loc[x, 'numLabel'] > args.max_label:
            image_db.loc[x, 'numClassifications'] = args.max_label
            image_db.loc[x, 'finalScore'] = posterior.divide(weight_ctr).max()
            image_db.loc[x, 'finalLabel'] = classes[np.asarray(posterior.divide(weight_ctr)).argmax()]
            #image_db.loc[x, 'finalLabel'] = posterior.divide(weight_ctr).idxmax()
            image_db.loc[x, 'tracks'] = [tracker]
            return

        classification = glitch[glitch.links_user == person]
        # if they classified the image multiple times, take the most recent classification
        if len(classification) > 1:
            classification = classification.iloc[-1]
        # save the correct confusion matrix
        matrix = matrices[matrices.id == int(classification.id)].conf_matrix.values[0]
        # for every image they classifiy as a certain type, a users contribution to the posterior for that type is the same for every image. Therefore, it is in our interest to pre-compute all of these values.
        post_contribution = matrix/np.sum(matrix, axis=1)
        # find the row associated with the annotation the user made
        row = int(classification.annotations_value_choiceINT)
        # grab the posterior contribution for that class, weighted by classification weight
        posteriorToAdd = float(classification.weight)*post_contribution[row, :]
        if np.isnan(posteriorToAdd).any():
            # FIXME: fixed the bug I think, but we should check this
            if idx == len(glitch.links_user)-1:
                image_db.loc[x, 'numClassifications'] = image_db.loc[x, 'numLabel']
                image_db.loc[x, 'finalScore'] = posterior.divide(weight_ctr).max()
                image_db.loc[x, 'finalLabel'] = classes[np.asarray(posterior.divide(weight_ctr)).argmax()]
                image_db.loc[x, 'tracks'] = [tracker]
            return
            else:
                continue
        # concatenate the new posterior contribution to tracker
        tracker = np.concatenate((tracker, np.asarray(posteriorToAdd)))
        # keep track of weighting counter for normalization purposes
        # FIXME we need to allow other definied weighting schemes...
        weight_ctr += float(classification.weight)
        # for now, only use posteriors for users that have seen and classified a golden image of this particular class
        # update image_db with the posterior contribution
        image_db.loc[x, classes] = image_db.loc[x, classes].add(np.asarray(posteriorToAdd).squeeze())
        # NOTE: normalize the posterior contribution when saved
        # add 1 to numLabels for all images
        image_db.loc[x, 'numLabel'] = image_db.loc[x, 'numLabel'] + 1
        # check if we have more than 1 label for an image and check for retirement
        # Check if posterior is above threshold, add 1 for the ML component
        #posterior = image_db.loc[x][classes].divide(image_db.loc[x]['numLabel'] + 1)
        posterior = image_db.loc[x][classes]
        if ((posterior.divide(weight_ctr) > ret_thresh).any() and image_db.loc[x, 'numLabel'] >= args.min_label):
            # save count that was needed to retire image
            image_db.loc[x, classes] = image_db.loc[x, classes].divide(weight_ctr)
            image_db.loc[x, 'numClassifications'] = image_db.loc[x, 'numLabel']
            image_db.loc[x, 'finalScore'] = posterior.divide(weight_ctr).max()
            image_db.loc[x, 'finalLabel'] = classes[np.asarray(posterior.divide(weight_ctr)).argmax()]
            #image_db.loc[x, 'finalLabel'] = posterior.divide(weight_ctr).idxmax()
            image_db.loc[x, 'retired'] = 1
            image_db.loc[x, 'cum_weight'] = weight_ctr
            image_db.loc[x, 'tracks'] = [tracker]
            return

       # if all people have been accounted for and image not retired, save info to image_db and tracks
        if idx == len(glitch.links_user)-1:
            image_db.loc[x, 'numClassifications'] = image_db.loc[x, 'numLabel']
            image_db.loc[x, 'finalScore'] = posterior.divide(weight_ctr).max()
            image_db.loc[x, 'finalLabel'] = classes[np.asarray(posterior.divide(weight_ctr)).argmax()]
            #image_db.loc[x, 'finalLabel'] = posterior.divide(weight_ctr).idxmax()
            image_db.loc[x, 'tracks'] = [tracker]
            return


print 'determining retired images...'
# sort data based on subjects number
subjects = combined_data.links_subjects.unique()
subjects.sort()

# implementation for multiprocessing
if multiproc:
    breakdown = np.linspace(0,len(subjects),args.num_cores+1)
    subjects = subjects[int(np.floor(breakdown[args.index-1])):int(np.floor(breakdown[args.index]))]
    image_db = image_db.loc[subjects]

# do the loop
for idx, g in enumerate(subjects):
    get_post_contribution(g)
    if idx%100 == 0:
        print '%.2f%% complete' % (100*float(idx)/len(subjects))

# save image and retirement data as pickles
if multiproc:
    image_db.to_pickle('../output/imageDB_'+args.file_name+str(args.index)+'.pkl')
else:
    image_db.to_pickle('../output/imageDB_'+args.file_name+'.pkl')
