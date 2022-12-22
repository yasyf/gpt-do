# `gpt-do`

This is a handy-dandy CLI for when you don't know wtf to do.

Instead of furiously grepping through man pages, simply use `do`, and have GPT-3 do all the magic for you.

## Demo

Click to play:

[![asciicast](https://asciinema.org/a/oXRkVfVsxvUFq4SFjrstgsZck.png)](https://asciinema.org/a/oXRkVfVsxvUFq4SFjrstgsZck?i=0.5&autoplay=1)

## Installation

We recommend using [`pipx`](https://pypa.github.io/pipx/):

```console
$ pipx install gpt-do
$ which do
```

However you can also use `pip`:

```console
$ pip install gpt-do
$ which do
```

```
## Usage

```console
$ export OPENAI_API_KEY=xxx # stick this in your bash_profile
$ do amend the message of my last commit to "It works!"
This command will amend the message of the last commit to 'It works!'.
git commit --amend -m 'It works!'
Do you want to continue? [y/N]: y
[main 3e6a2f6] It works!!
 Date: Thu Dec 22 01:15:40 2022 -0800
 5 files changed, 1088 insertions(+)
 create mode 100644 .gitignore
 create mode 100644 .gitmodules
 create mode 100644 README.md
 create mode 100644 poetry.lock
 create mode 100644 pyproject.toml
```
