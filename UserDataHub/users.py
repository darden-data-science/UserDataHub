from traitlets.config import LoggingConfigurable
from traitlets import Bool, Integer, Set, Unicode, Dict, Any, default, Instance

import yaml
# import hashlib
import os
import shutil
# import subprocess
from pathlib import Path
import copy
import math
import logging

from collections.abc import Mapping
from functools import lru_cache, reduce, partial


def merge(a, b, append=False):
    """
    This allows me to merge basically anything. I can also append or
    overwite. For append, lists are appended, booleans take the max value
    seen (so if one is true, then the final is true), and strings are
    concatenated.
    """
    from collections.abc import Mapping
    from numbers import Number
    merged = b
    if append and not b:
        merged = a
    if isinstance(a, list) and isinstance(b, list):
        merged = _merge_lists(a, b, append)
    elif isinstance(a, str) and isinstance(b, str):
        merged = _merge_strings(a, b, append)
    elif isinstance(a, Mapping) and isinstance(b, Mapping):
        merged = _merge_dictionaries(a, b, append)
    return merged

def _merge_lists(a, b, append=False):
    merged = b.copy()
    if append:
        temp_list = a
        temp_list.extend(x for x in b if x not in temp_list)
        merged = temp_list
    return merged

def _merge_strings(a, b, append=False):
    merged = b
    if append:
        merged = a + b
    return merged

def _merge_dictionaries(a,b, append=False):
    """Merge two dictionaries recursively.
    Simplified From https://stackoverflow.com/a/7205107
    and further modified from z2jh.py to merge lists and strings.
    """
    from collections.abc import Mapping
    merged = a.copy()
    for key in b:
        if key in a:
            merged[key] = merge(a[key], b[key], append)
        else:
            merged[key] = b[key]
    return merged


def safeget(dct, keys, default=None):
    """
    This allows me to get keys in a nested dictionary safely when I'm not
    sure if the final key or any parent keys exist. Note that when the key
    list is an empty list, it just returns the dictionary. This is intended
    behavior.
    """
    # if not keys or len(keys) == 0:
    #     return default
    for key in keys:
        try:
            dct = dct[key]
        except KeyError:
            return default
        except TypeError:
            return default
    return dct

def intersperse(lst, item, prepend_if_nonzero=False):
    """
    This will allow me to intersperse something throughout a list.
    I also have the option to prepend if the list is nonzero. This helps me drill down better.
    """
    result = [item] * (len(lst) * 2 - 1)
    result[0::2] = lst
    if len(lst) > 0 and prepend_if_nonzero:
        result = [item] + result
    return result

def get_list_of_keys(d_or_l, keys_list):
    """
    This allows me to get all keys in a dictionary recursively. I use this
    to check to see if profile_list is set anywhere in the user specific
    config. If it is, then I have to use the custom options form
    approach. If not, I can start all servers at the same time.
    """
    if isinstance(d_or_l, dict):
        for k, v in iter(sorted(d_or_l.items())):
            if isinstance(v, list):
                get_list_of_keys(v, keys_list)
            elif isinstance(v, dict):
                get_list_of_keys(v, keys_list)
            keys_list.append(k)   #  Altered line
    elif isinstance(d_or_l, list):
        for i in d_or_l:
            if isinstance(i, list):
                get_list_of_keys(i, keys_list)
            elif isinstance(i, dict):
                get_list_of_keys(i, keys_list)
    # return keys_list


def gitpuller_string(git_repos):
    r"""
    This constructs the final gitpuller string to pass as an environmental
    variable. Individual repos are separated by "\`", and the elements of
    the repo are separated by "^".
    """
    if not git_repos:
        return ""
    gp_string = ""
    unique_repos = []
    for repo in git_repos:
        if repo not in unique_repos:
            unique_repos.extend([repo])
    for git_pull in unique_repos:
        if not type(git_pull) is dict:
            continue
        if not git_pull.get('url'):
            continue
        if not git_pull.get('branch'):
            git_pull['branch'] = "master"
        if not git_pull.get('folder'):
            git_pull['folder'] = git_pull['url'].rsplit('/', 1)[-1]
        if git_pull.get('subfolder'):
            git_pull['subfolder'] = Path(git_pull.get('subfolder'))
            git_pull['folder'] = git_pull['subfolder'].joinpath(git_pull['folder'])
        # git_pull['folder'] = Path("${HOME}").joinpath(git_pull['folder'])
        git_pull_string = "^".join([git_pull.get('url'),
                                    git_pull.get('branch'),
                                    str(git_pull.get('folder'))])
        gp_string = r"\`".join([gp_string, git_pull_string])
    return gp_string



def modify_gitPuller_folder(subfolder, gitPuller):
    """
    This modifies the gitpuller entry so that the repo is cloned into a
    subsection (or group) if the section that it is in is below the root
    section for the user.
    """
    for git_repo in gitPuller:
        if type(git_repo) is not dict:
            continue
        else:
            git_repo['subfolder'] = subfolder.joinpath(git_repo.get("subfolder", ""))



def create_directory(path, uid=1000, gid=1000, mode=0o750, sticky_bit=False):
    """
    Helper function to create directories with the proper ownership and permissions.
    """
    import stat
    effective_mode = mode
    if sticky_bit:
        effective_mode = stat.S_ISGID | mode
    path.mkdir(mode=0o750, exist_ok=True)
    # os.chown(str(path), uid, gid)
    path.chmod(mode=effective_mode)



class UserConfigurator(LoggingConfigurable):

    enable_custom_allowed = Bool(
        default_value=False,
        help="""
        Whether or not to only allow users in the list.
        """
    ).tag(config=True)

    def __init__(self, 
                 section_dict, 
                 root_path = None, 
                 enable_custom_allowed = False,
                 **kwargs):

        super().__init__(**kwargs)

        self.log.info("Initializing the UserConfigurator")
        self.section_dict = self.get_section_dict(section_dict)
        self.user_dict = self.get_user_dict()
        if enable_custom_allowed is not None:
            self.enable_custom_allowed = enable_custom_allowed



    def get_user_data(self, username):
        """
        This returns the user data if it exists. If not, it initializes it to default.
        """
        if username in self.user_dict:
            return self.user_dict[username]
        elif self.enable_custom_allowed:
            # If the user is not in the user_dict, then return None.
            return None
        else:
            user_data = self.create_user_dict(username)
            return user_data

    def create_user_dict(self, username, path = []):
        """
        Creates the user dict if it doesn't exist.
        """
        
        self.log.info("Creating user dictionary for user %r." % username)

        section_data = self.get_section_data(username, path)

        default_user_data = {"admin": False,
                             "sections": [section_data],
                             "root": copy.deepcopy(path)}

        return default_user_data

    def get_section_data(self, username, path):
        """
        Get's the default section dict for a user dict.
        """

        section_data = safeget(self.section_dict, self.get_section_dict_key(path), {})

        user_section_data = {'section_path': copy.deepcopy(path),
                             'groups': [],
                             'config': {
                                'configAppend': copy.deepcopy(section_data.get('configAppend', {})) or {},
                                'configOverride': copy.deepcopy(section_data.get('configOverride', {})) or {},
                                },
                             'user_config': {
                                'configAppend': copy.deepcopy(safeget(section_data, ['users', username, 'configAppend'], {})) or {},
                                'configOverride': copy.deepcopy(safeget(section_data, ['users', username, 'configOverride'], {})) or {}
                                }
                            }

        if type(section_data.get('groups')) is dict:
            for group, group_data in section_data.get('groups', {}).items():
                if username in group_data.get('members', []) or safeget(group_data, ['properties', 'everyone'], False):
                    user_section_data['groups'].append({'group_name': group,
                                                        'readOnly': safeget(group_data, ['properties', 'readOnly'], False),
                                                        'config': {
                                                            'configAppend': copy.deepcopy(group_data.get('configAppend', {})) or {},
                                                            'configOverride': copy.deepcopy(group_data.get('configOverride', {})) or {},
                                                            }
                                                        })
        
        user_section_data["groups"].sort(key = lambda x: x["group_name"])

        return user_section_data


    def get_section_dict_key(self, section_list, sub_item_list = []):
        """
        Get the key to access the section dict for information
        """
        return intersperse(section_list, "sections", prepend_if_nonzero=True) + sub_item_list



    def get_users_from_sections(self, user_dict=None, path=None):
        """
        This creates the user dictionary that includes the section the user is
        in, the groups that they are in, and the relevant configuration
        parameters.
        """

        if user_dict is None:
            user_dict = {}
        if path is None:
            path = []

        section_key = self.get_section_dict_key(path)
        section_data = safeget(self.section_dict, section_key)

        if type(section_data.get("users")) is dict:
            for user, user_data in section_data.get("users", {}).items():
                if user not in user_dict:

                    user_dict[user] = self.create_user_dict(user, path=path)

                else:
                    user_section_data = self.get_section_data(user, path)
                    user_dict[user]["sections"].append(user_section_data)
                    if len(user_dict[user]["root"]) > len(path):
                        user_dict[user]["root"] = path

                if type(user_data) is dict:
                    # This makes it so that if you are set as an admin anywhere, you
                    # are always an admin.
                    user_dict[user]["admin"] = max(user_dict[user]["admin"],
                                                user_data.get("admin", False))

        # Now we recurse through the sections adding sections as we find them.
        # Since a dict is mutable, we don't have to pass it back and forth.
        # It is updated in place.
        if type(section_data.get("sections")) is dict:
            for section, section_data in section_data.get("sections", {}).items():
                self.get_users_from_sections(user_dict = user_dict, path = path + [section])

        return user_dict

    def get_user_root(self, username, user_data):
        full_section_list = []
        # Add all sublists to the section list
        section_list = []
        for section in user_data.get("sections", []):
            section_path = section.get('section_path')
            section_list.append(section_path)

        for section_path in section_list:
            full_section_list = full_section_list + [section_path[0:i] for i in range(len(section_path) + 1)]
        # Make the sublists unique
        unique_section_list = [list(x) for x in set(tuple(x) for x in full_section_list)]

        for section_path in unique_section_list:
            if section_path not in section_list:
                user_data['sections'].append(self.get_section_data(username, section_path))

        # Sort the sublists so that we can deterministically determine the order of merging configs
        user_data["sections"].sort(key = lambda x: (len(x['section_path']), x["section_path"]))

        user_data["root"] = []

        return user_data

    def get_section_dict(self, section_info):
        """
        Gets the section dictionary.
        """
        # section_dict = self.add_uid_section_group(section_info)
        return section_info

    def get_user_dict(self):
        """
        Gets the user dictionary.
        """
        self.log.info("Getting the user_dict.")
        # Get the user_dict with all explicitly set sections
        # add_uid_section_group(section_dict)
        user_dict = self.get_users_from_sections()

        # Now we get the paths from root to each section. Once we sort these, we
        # will be able to get the root.
        for user, user_data in user_dict.items():
            user_dict[user] = self.get_user_root(user, user_data)
            # user_dict[user] = self.get_user_groups(user_data)

        return user_dict





class NFSUserConfigurator(UserConfigurator):

    root_path = Any(
        default_value="/mnt/efs",
        allow_none=False,
        help="""
        The path to the root of the data folder.
        """
    ).tag(config=True)

    nfs_pvc_name_readwrite = Unicode(
        default_value="nfs-data-readwrite",
        allow_none=False,
        help="""
        The name of the PVC that the user container should use for readwrite nfs data.
        """
    ).tag(config=True)

    nfs_pvc_name_readonly = Unicode(
        default_value="nfs-data-readonly",
        allow_none=False,
        help="""
        The name of the PVC that the user container should use for read only nfs data.
        """
    ).tag(config=True)

    user_section_base_folder = Unicode(
        default_value="/mnt/efs",
        allow_none=False,
        help="""
        The location that will be the root path for mounting group folders.
        """
    ).tag(config=True)

    profile_files_folder = Unicode(
        default_value="/etc/userdatahub/profile_files",
        allow_none=False,
        help="""
        The location that will house files to copy to the user directories.
        """
    ).tag(config=True)

    def __init__(self, 
                 section_dict, 
                 root_path = None, 
                 enable_custom_allowed = None,
                 **kwargs):
        super().__init__(section_dict, root_path, enable_custom_allowed, **kwargs)
        self.log.info("Initializing the NFSUserConfigurator")

        if root_path is not None:
            self.root_path = root_path

        self.root_path = Path(self.root_path)

        print("NFSUserConfigurator is creating the necessary file structure...")
        self.create_file_structure()


    # Starting the code to create the file structure.
    def create_file_structure(self):
        """
        This creates the initial file structure.
        """
        self.create_base_folders(self.section_dict, self.root_path)
        return

    def create_base_folders(self, section_dict, root_path):
        """
        Create all folders for all sections and the sub folders for groups and users.
        This recurses so it needs the section_dict given explicitly.
        """
        # section_uid = section_dict["section_uid"]
        section_uid = 1000
        create_directory(root_path, gid=section_uid, mode=0o750)

        # Create groups folder
        if type(section_dict.get("groups")) is dict:
            if len(section_dict.get("groups")) > 0:
                create_directory(root_path.joinpath("groups/"), gid=section_uid, mode=0o750)
                self.create_group_folders(section_dict, root_path.joinpath("groups/"))
        # if type(section_dict.get("users")) is dict:
        #     if len(section_dict.get("users")) > 0:

        # # Create users folder
        # if type(section_dict.get("users")) is dict:
        #     if len(section_dict.get("users")) > 0:
        #         create_directory(root_path.joinpath("users/"), gid=section_uid)

        # Create sections folder and recurse
        if type(section_dict.get("sections")) is dict:
            if len(section_dict.get("sections")) > 0:
                create_directory(root_path.joinpath("sections/"), gid=section_uid, mode=0o750)
            for subsection, section_data in section_dict.get("sections", {}).items():
                self.create_base_folders(section_data, root_path.joinpath(Path("sections/" + subsection)))
        return

    def create_group_folders(self, section_dict, root_path):
        """
        Create all group folders in the section.
        """
        
        # section_admin_uid = section_dict.get("section_admin_uid", 0)
        if type(section_dict.get("groups")) is dict:
            for group, group_data in section_dict.get("groups", {}).items():
                if type(group_data) is dict:
                    mode = 0o750
                    group_uid = 1000
                    create_directory(root_path.joinpath(group), gid=group_uid, mode=mode, sticky_bit=True)
        return

    def create_home_folder(self, username):
        """
        This function will set up the home folders for the user.
        """

        self.parent.log.info("Initializing home folder for %r." % username)

        user_data = self.get_user_data(username)

        # If you don't have a valid authname, no reason to make your folders.
        if user_data.get('authName') == 'null_authName_invalid':
            return
        # uid = user_data["uid"]
        uid = 1000
        mode = 0o750
        root = user_data.get("root", [])
        # username = user_data.get("username", user)
        if len(root) > 0:
            users_folder = self.root_path.joinpath("sections/" + "/sections/".join(root) + "/users/")
        else:
            users_folder = self.root_path.joinpath("users/")
        # This creates the user folder when we first see someone with that root
        create_directory(users_folder,
                        gid = 1000,
                        mode = 0o750)
        user_folder = users_folder.joinpath(username + "/")
        create_directory(user_folder, uid = uid, gid = uid, mode = mode)
        # trash_folder = self.root_path.joinpath(".Trash-" + str(uid) + "/")
        # create_directory(trash_folder, uid=uid, gid=uid, mode=mode)
        # I need to set up the profile files
        skel_path = Path(self.profile_files_folder)
        if skel_path.is_dir():
            for root, dirs, files in os.walk(skel_path, followlinks=True):
                relative_path = os.path.relpath(root, skel_path)
                for file_ in files:
                    if not user_folder.joinpath(relative_path).joinpath(file_).exists():
                        shutil.copy(Path(root).joinpath(file_), user_folder.joinpath(relative_path).joinpath(file_))
                        # os.chown(user_folder.joinpath(relative_path).joinpath(file_), uid=1000, gid=1000)
                for dir_ in dirs:
                    create_directory(user_folder.joinpath(relative_path).joinpath(dir_))
                    # os.chown(user_folder.joinpath(relative_path).joinpath(dir_), uid=1000, gid=1000)

            # for file in skel_path.iterdir():
            #     if not user_folder.joinpath(file.name).exists():
            #         shutil.copy(file, user_folder.joinpath(file.name))
            #         # os.chown(user_folder.joinpath(file.name), uid=uid, gid=uid)
        self.symlink_group_folders(user_folder, user_data)
        return


    def symlink_group_folders(self, user_folder, user_data):
        root = user_data.get("root", [])
        # uid = user_data["uid"]
        uid = 1000
        mode = 0o750
        for section in user_data.get('sections', []):
            for group in section.get('groups', []):
                section_path = section.get('section_path')

                sections = []
                for section_name in section_path[len(root):]:
                    sections = sections + [section_name]
                    create_directory(Path(user_folder).joinpath("/".join(sections)),
                                    uid = uid,
                                    gid = uid,
                                    mode=mode)
                
                src = Path(user_folder).joinpath("/".join(section_path)).joinpath(group["group_name"])
                dest = Path(self.user_section_base_folder).joinpath("/".join(intersperse(section_path, 'sections', prepend_if_nonzero=True) 
                                                                             + ["groups", group['group_name']]))

                # This handles a pre-existing symlink. Note that I'm assuming the
                # destination is absolute, so I have to know where the mount point
                # is going to be.
                counter = 0
                if os.path.lexists(src) and (src.resolve() == Path(dest).resolve()):
                    continue
                elif os.path.lexists(src) and (src.resolve() != Path(dest).resolve()):
                    new_src=src
                    while os.path.lexists(new_src) and (new_src.resolve() != Path(dest).resolve()):
                        counter = counter + 1
                        new_src = src.parent.joinpath(src.name + " (" + str(counter) + ")")
                    if new_src.resolve() == Path(dest).resolve():
                        continue
                    src = new_src

                src.symlink_to(dest, target_is_directory=True)
                # os.chown(src, uid=1000, gid=1000, follow_symlinks=False)
        return


    def get_user_dict(self):
        self.user_dict = super().get_user_dict()
        for _, user_data in self.user_dict.items():
            self.get_extra_volumes(user_data)
            self.get_extra_volume_mounts(user_data)

        return self.user_dict

    def get_user_data(self, username):
        """
        This returns the user data if it exists. If not, it initializes it to default.
        """
        if username in self.user_dict:
            return self.user_dict[username]
        elif self.enable_custom_allowed:
            # If the user is not in the user_dict, then return None.
            return None
        else:
            user_data = self.create_user_dict(username)
            user_data = self.get_extra_volumes(user_data)
            user_data = self.get_extra_volume_mounts(user_data)
            return user_data

    def get_extra_volumes(self, user_data):
        """
        This gets the extra volumes and appends them to the last user_config so they cannot be overridden.
        """
        # user_data = self.user_dict[username]

        last_section = user_data.get('sections', [])[-1]
        extra_volumes = [
            {'name': 'nfs_readwrite',
             'persistentVolumeClaim': {
                 'claimName': self.nfs_pvc_name_readwrite}},
            {'name': 'nfs_readonly',
             'persistentVolumeClaim': {
                 'claimName': self.nfs_pvc_name_readonly}},
        ]

        last_section['user_config']['configAppend']['volumes'] = merge(last_section['user_config']['configAppend'].get('volumes', None), extra_volumes, append=True)

        return user_data


    def get_extra_volume_mounts(self, user_data):
        """
        This gets the extra volume mounts and appends them to the last user_config so they cannot be overridden.
        """


        last_section = user_data.get('sections', [])[-1]


        extra_volume_mounts = []
        for section in user_data.get('sections', []):
            for group in section.get('groups', {}):
                if group.get('readOnly', False):
                    volume_name = 'nfs_readonly'
                else:
                    volume_name = 'nfs_readwrite'
                volume_mount = {
                    'mountPath': self.user_section_base_folder + "/"
                                    + '/'.join(intersperse(section['section_path'], 'section', prepend_if_nonzero=True) + ['groups', group['group_name']]),
                    'subPath': '/'.join(intersperse(section['section_path'], 'section', prepend_if_nonzero=True))
                                    + '/groups/' + group['group_name'],
                    'name': volume_name
                }
                extra_volume_mounts.append(volume_mount)

        last_section['user_config']['configAppend']['volume_mounts'] = merge(last_section['user_config']['configAppend'].get('volume_mounts', None), extra_volume_mounts, append=True)
        return user_data







def main():
    test_path = Path(__file__).parent.parent.absolute().joinpath((Path('tests/test.yaml')))
    print(test_path)
    with open(test_path, 'r') as f:
        test_dict = yaml.full_load(f)

    configurator = NFSUserConfigurator(test_dict['class'])
    user_dict = configurator.user_dict
    
    for user in user_dict.keys():
        configurator.create_home_folder(user)

    # for user in user_dict.keys():
    #     configurator.get_extra_volumes(user)
    #     configurator.get_extra_volume_mounts(user)

    print(configurator.get_user_data("new_user"))

    with open(Path(__file__).parent.parent.absolute().joinpath((Path('test_output.yaml'))), 'w') as f:
        f.write(yaml.dump(user_dict, default_flow_style=False))

if __name__=="__main__":
    main()