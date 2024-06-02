# SillyTavern-i18n

Tools for working with frontend localization files.

## Features

1. Automatically add new keys to translate from HTML files.
2. Prune missing keys from localization files.
3. Use automatic Google translation to auto-populate missing values.
4. Sort JSON files by keys.

## Usage

Dependencies: Python 3.10

1) Install the requirements.

```bash
pip install -r ./requirements.txt
```

2) Run `generate.py` **while in the SillyTavern directory**.

```bash
usage: generate.py [-h] [-d DIRECTORY] [--auto-add] [--auto-remove] [--sort-keys]
                   json

Update or Generate i18n JSON files

positional arguments:
  json                  JSON file path

options:
  -h, --help            show this help message and exit
  -d DIRECTORY, --directory DIRECTORY
                        Directory path
  --auto-add            Auto add missing keys
  --auto-remove         Auto remove extra keys
  --sort-keys           Sort keys as they appear in i18n dataset
```

Example:

```bash
cd ~/SillyTavern
python ~/SillyTavern-i18n/generate.py zh-cn --sort-keys
```

## License and credits

AGPLv3

* Original idea and implementation by (Zhongyi-Lu)[https://github.com/Zhongyi-Lu]
* Improvements by (steve02081504)[https://github.com/steve02081504]
