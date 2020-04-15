# Copyright 2019 TerraPower, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Settings are various key-value pairs that determine a bunch of modeling and simulation behaviors.

They are one of the key inputs to an ARMI run. They say which modules to run and which
modeling approximations to apply and how many cycles to run and at what power and
availability fraction and things like that. The ARMI Framework itself has many settings
of its own, and plugins typically register some of their own settings as well.
"""
import fnmatch
import os
import glob
import shutil
from typing import Union

from ruamel import yaml

import armi
from armi import runLog
from armi.localization import exceptions
from armi.settings.caseSettings import Settings
from armi.utils import pathTools

from armi.settings.setting import Setting

NOT_ENABLED = ""  # An empty setting value implies that the feature


def isBoolSetting(setting:Setting) -> bool:
    """Return whether the passed setting represents a boolean value."""
    return isinstance(setting.default, bool)


def recursivelyLoadSettingsFiles(
    rootDir, patterns, recursive=True, ignorePatterns=None, handleInvalids=True
):
    """
    Scans path for valid xml files and returns their paths.

    Parameters
    ----------
    rootDir : str
        The base path to scan for settings files
    patterns : list
        file patterns to match file names
    recursive : bool (optional)
        load files recursively
    ignorePatterns : list (optional)
        list of filename patterns to ignore
    handleInvalids : bool
        option to suppress errors generated when finding files that appear to be settings files but fail to load. This
        may happen when old settings are present.

    Returns
    -------
    csFiles : list
        list of :py:class:`~armi.settings.caseSettings.Settings` objects.
    """
    possibleSettings = []
    runLog.info("Finding potential settings files matching {}.".format(patterns))
    if recursive:
        for directory, _list, files in os.walk(rootDir):
            matches = set()
            for pattern in patterns:
                matches |= set(fnmatch.filter(files, pattern))
            if ignorePatterns is not None:
                for ignorePattern in ignorePatterns:
                    matches -= set(fnmatch.filter(files, ignorePattern))
            possibleSettings.extend(
                [os.path.join(directory, fname) for fname in matches]
            )
    else:
        for pattern in patterns:
            possibleSettings.extend(glob.glob(pattern))

    csFiles = []
    runLog.info("Checking for valid settings files.")
    for possibleSettingsFile in possibleSettings:
        if os.path.getsize(possibleSettingsFile) > 1e6:
            runLog.info("skipping {} -- looks too big".format(possibleSettingsFile))
            continue
        try:
            cs = Settings()
            cs.loadFromInputFile(possibleSettingsFile, handleInvalids=handleInvalids)
            csFiles.append(cs)
            runLog.extra("loaded {}".format(possibleSettingsFile))
        except exceptions.InvalidSettingsFileError as ee:
            runLog.info("skipping {}\n    {}".format(possibleSettingsFile, ee))
        except yaml.composer.ComposerError as ee:
            runLog.info(
                "skipping {}; it appears to be an incomplete YAML snippet\n    {}".format(
                    possibleSettingsFile, ee
                )
            )
        except Exception as ee:
            runLog.error(
                "Failed to parse {}.\nIt looked like a settings file but gave this exception:\n{}: {}".format(
                    possibleSettingsFile, type(ee).__name__, ee
                )
            )
            raise
    csFiles.sort(key=lambda csFile: csFile.caseTitle)
    return csFiles


def promptForSettingsFile(choice=None):
    """
    Allows the user to select an ARMI input from the input files in the directory

    Parameters
    ----------
    choice : int, optional
        The item in the list of valid XML files to load

    """
    runLog.info("Welcome to the ARMI Loader")
    runLog.info("Scanning for ARMI settings files...")
    files = glob.glob("*.yaml") + glob.glob("*.xml")  # phase out xml later
    if not files:
        runLog.info(
            "No eligible settings files found. Creating settings without choice"
        )
        return None

    if choice is None:
        for i, pathToFile in enumerate(files):
            runLog.info("[{0}] - {1}".format(i, os.path.split(pathToFile)[-1]))
        choice = int(input("Enter choice: "))

    return files[choice]


def getMasterCs():
    """
    Return the global case-settings object (cs).

    This can be called at any time to create or obtain the master Cs, a module-level CS
    intended to be shared by many other objects.

    It can have multiple instances in multiprocessing cases.

    Returns
    -------
    cs : Settings
        The loaded cs object
    """
    cs = Settings.instance
    if cs is None:
        cs = Settings()
        setMasterCs(cs)
    return cs


def setMasterCs(cs):
    """
    Set the master Cs to be the one that is passed in.

    These are kept track of independently on a PID basis to allow independent multiprocessing.
    """
    Settings.instance = cs
    runLog.debug("Master cs set to {} with ID: {}".format(cs, id(cs)))


def convertSettingsFromXMLToYaml(cs):
    if not cs.path.endswith(".xml"):
        raise ValueError("Can only convert XML files")

    old = cs.path
    oldCopy = old + "-converted"
    newNameBase, _ext = os.path.splitext(old)
    newName = newNameBase + ".yaml"
    counter = 0
    while os.path.exists(newName):
        # don't overwrite anything
        newName = "{}{}.yaml".format(newNameBase, counter)
        counter += 1
    if counter:
        runLog.warning(
            "{} already exists in YAML format; writing {} instead".format(
                newNameBase, newName
            )
        )

    runLog.info(
        "Converting {} to new YAML format. Old copy will remain intact as {}".format(
            old, oldCopy
        )
    )
    cs.writeToYamlFile(newName)
    cs.path = newName
    shutil.move(old, oldCopy)
