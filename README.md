# Aptly cleaner
Cleaning Aptly repository with set of predefined rules

Consists of two tools:
* aptly_cleaner.py
* file_cleaner.py

## aptly_cleaner.py
This tool will clean your setted Aptly repositories with set of predefined rules.
Check `config.conf.example` for explanation on all settings.
Basically you need to set days for packages to live, max versions of one package in repostitory and set list of repositories.

Then script will clean all repositories in all defined statuses. Higher priority means that this status will be cleaned before those with smaller priority.

**Also**, if package version exists in higher priority repository - it will not be deleted, even if it falls under specified rules.

### Parameters
`-c / --config` - **required**. Path to config to use.

`-v / --verbose` - Turn on verbose messages

`--dry-run` - Do not delete anything, just show actions

`-r / --only-from-repo` - Delete packages only from repository, not from File System

`--calc` - This option will calculate saved size by this tool. Forces `--dry-run`, so will not delete anything

`--force-invalid-user` - Use invalid user(not that specified in config) for running this script

## file_cleaner.py
This tool will search for all packages, in directories that you specified in config, that exist, but not in any of repositories and will delete them, if you want so.

### Parameters
`-c / --config` - **required**. Path to config. Both tools can use one config

`-v / --verbose` - Output verbose messages

`-r / --remove` - Also remove found packages

`--dry-run` - Even if `-r` is specified do not remove anything
