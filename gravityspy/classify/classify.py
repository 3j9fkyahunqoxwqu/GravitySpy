# -*- coding: utf-8 -*-
# Copyright (C) Scott Coughlin (2017-)
#
# This file is part of gravityspy.
#
# gravityspy is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# gravityspy is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with gravityspy.  If not, see <http://www.gnu.org/licenses/>.

from ..utils import log
from ..utils import utils

import os

def classify(event_time, channel_name,
             project_info_pickle, path_to_cnn,
             verbose=True, **kwargs):
    """classify an excess noise event

    Note:
        If you do not pass the **kwargs `timeseries`
        or `source` then your timeseries will attempt to be
        generated on the fly uses `gwpy.timeseries.TimeSeries.get`

    Parameters:

        event_time (list):
            A list of `gwpy.spectrogram.Spectrogram` objects

        channel_name (array):
            The min and max of the colorbar for the plots

        project_info_pickle (array):
            The duration assosciated with each plot to be made

        path_to_cnn (str):
            What detetor where these spectrograms from

        **kwargs:
            timeseries
            source

    Returns:

        ind_fig_all
            A list of individual spectrogram plots
        super_fig
            A single `plot` object contianing all spectrograms
    """

    if not os.path.isfile(path_to_cnn):
        raise ValueError('The provided cnn model does not '
                         'exist.')

    logger = log.Logger('Gravity Spy: Classifying Event')

    # Extract Detector Name From Channel Name
    detector_name = channel_name.split(':')[0]

    # Parse Keyword Arguments
    config = kwargs.pop('config', utils.GravitySpyConfigFile())
    plot_directory = kwargs.pop('plot_directory', 'plots')

    # Parse Ini File
    plot_time_ranges = config.plot_time_ranges
    plot_normalized_energy_range = config.plot_normalized_energy_range

    # Cropping the results before interpolation to save on time and memory
    # perform the q-transform
    specsgrams, q_value = utils.make_q_scans(event_time=event_time,
                                             channel_name=channel_name,
                                             config=config,
                                             **kwargs)

    utils.save_q_scans(plot_directory, specsgrams,
                       plot_normalized_energy_range, plot_time_ranges,
                       detector_name, event_time,
                       **kwargs)


    results = utils.label_q_scans(plot_directory=plot_directory,
                                  path_to_cnn=path_to_cnn,
                                  project_info_pickle=project_info_pickle,
                                  **kwargs)
    results['q_value'] = q_value

    return results