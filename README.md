# SillyTavern-i18n

Tools for working with frontend localization files.

## Usage

```bash
~/workstation/SillyTavern-i18n pr/2@e309665
1 file >pip install -r ./requirements.txt *> null

~/workstation/SillyTavern-i18n pr/2@e309665
1 file >cd /e/SillyTavern/

E:\SillyTavern pr/2336@886de3ca
 sillytavern@1.12.0 >py ~/workstation/SillyTavern-i18n/generate.py -h
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

E:\SillyTavern pr/2336@886de3ca
 sillytavern@1.12.0 >py ~/workstation/SillyTavern-i18n/generate.py zh-cn --sort-keys
Key '' not found in './public\locales\zh-cn.json'.
Done!

E:\SillyTavern pr/2336@886de3ca
 sillytavern@1.12.0 >py ~/workstation/SillyTavern-i18n/generate.py '' --sort-keys
Updating all JSON files...
Done!
```
