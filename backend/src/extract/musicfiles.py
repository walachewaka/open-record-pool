#!/usr/bin/env python3
"""
Extract the information about the music files.
"""

import os
import time
import asyncio
import aiofiles
import hashlib
import pathlib

import mutagen

# Constant for the volume where the music files are.
MUSIC_PATH = '/music'


async def get_checksum_for_file(file_name):
    """
    Gets the checksum for a file.
    """
    checksum = ""
    async with aiofiles.open(file_name, mode='rb') as f:
        contents = await f.read()
        checksum = hashlib.md5(contents).hexdigest()
    return checksum


async def _traverse_target_tree_async(target_dir):
    """
    Recursively traverses the target directory [target_dir]
    and yields a sequence of file names.
    """
    root = pathlib.Path(target_dir)
    # Patterns to pathlib.Path.glob are the same as for fnmatch
    # ** means this directory and all subdirectories, recursively
    # FIXME: Using the ** pattern in large directories trees may consume an inodinate amount of time.
    for path in root.glob('**/*.mp3'):
        yield path.absolute()


async def _extract_transform_load_one_file(file_name):
    print(f"--- Extract info from file: {file_name} ---")
    checksum = await get_checksum_for_file(file_name)
    # Extract the MP3 tags
    # FIXME: Use a aiofiles file-like object for mutagen
    mutagen_file = mutagen.File(file_name)
    print(f" - Checksum: {checksum}")
    print(f" - Info:     {mutagen_file}")
    # TODO: Transform and cleanup the MP3 tags
    # TODO: Load the infos into the database
    # TODO: Save the modified MP3 tags to the MP3 file
    # (cannot work with a read-only volume)
    return mutagen_file.pprint()


async def _extraction_job():
    """
    Extracts the information about all the music files. (in another thread)
    """
    global MUSIC_PATH
    ret = []
    async for f in _traverse_target_tree_async(MUSIC_PATH):
        ret.append(await _extract_transform_load_one_file(f))
    return ret


async def extract_music_files_info():
    """
    Extracts the information about all the music files.
    """
    # TODO ret = await asyncio.to_thread(_extraction_job)
    ret = await _extraction_job()
    print(f"finished extracting music files info at {time.strftime('%X')}")
    return ret


async def list_all_music_files_info():
    """
    For now, this extracts all the info and returns it.
    What we want is to return only the info that is stored in the database.
    """
    # TODO: Move this to another file
    # TODO: Return the info stored in the database.
    return await extract_music_files_info()

