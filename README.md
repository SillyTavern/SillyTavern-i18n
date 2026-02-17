# SillyTavern-i18n

Tools for working with frontend localization files.

## Features

1. Automatically add new keys from HTML `data-i18n` attributes.
2. Extract keys from scripts (`t` template tag and `translate(...)`).
3. Prune missing keys from localization files.
4. Use automatic Google translation to auto-populate missing values.
5. Sort JSON files by project tree order (source path + first appearance in file).

## Usage

```txt
usage: generate.py [-h] [-d DIRECTORY] [--auto-add] [--auto-translate] [--auto-remove] [--sort-keys]
                   json

Update or Generate i18n JSON files

positional arguments:
  json                  JSON file path

options:
  -h, --help            show this help message and exit
  -d DIRECTORY, --directory DIRECTORY
                        Directory path
  --auto-add            Auto add missing keys
  --auto-translate      Auto translate missing keys when they are added
  --auto-remove         Auto remove extra keys
  --sort-keys           Sort keys by project tree order (source path + first appearance in file)
```

Dependencies: Python 3.10 and up.

1) Install the requirements.

```bash
pip install -r ./requirements.txt
```

2) Run `generate.py` **while in the SillyTavern directory**.

Example (update for `zh-cn` file, sort keys):

```bash
cd ~/SillyTavern
python ~/SillyTavern-i18n/generate.py zh-cn --sort-keys
```

3) Commit and PR changes to the SillyTavern repository.

## License and credits

AGPLv3

* Original idea and implementation by [Zhongyi-Lu](https://github.com/Zhongyi-Lu)
* Improvements by [steve02081504](https://github.com/steve02081504)
