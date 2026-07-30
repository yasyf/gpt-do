# `gpt-do`

Turn natural-language requests into reviewed shell commands using a current OpenAI
model and the Responses API.

This fork modernizes the original project by replacing retired completion models
and the pre-1.0 OpenAI SDK. Use `do` (or `ddo` in `bash`/`zsh`) when you do not
remember the command you need.

Check out the blog post [here](https://musings.yasyf.com/never-write-a-bash-command-again-with-gpt-3/).

## Demo

Click to play:

[![asciicast](https://asciinema.org/a/oXRkVfVsxvUFq4SFjrstgsZck.png)](https://asciinema.org/a/oXRkVfVsxvUFq4SFjrstgsZck?i=0.5&autoplay=1)

## Installation

Install this fork with [`pipx`](https://pipx.pypa.io/):

```console
$ brew uninstall yasyf/do/do # only if the old Homebrew formula is installed
$ pipx install git+https://github.com/andrew12-forge/gpt-do.git
$ which do
~/.local/bin/do
```

## Usage

**n.b.** If you're on `bash` or `zsh`, `do` is a reserved keyword, so you'll have to use the alias `ddo`.

Set `OPENAI_API_KEY` before running the command. The default model is
`gpt-5-mini`; pass any supported Responses API model with `--model`.

```console
$ export OPENAI_API_KEY=xxx
$ ddo --model gpt-5-mini amend the message of my last commit to "It works!"
This command will amend the message of the last commit to 'It works!'.
git commit --amend -m 'It works!'
Execute this command? [Y/n]: y
[main 3e6a2f6] It works!!
 Date: Thu Dec 22 01:15:40 2022 -0800
 5 files changed, 1088 insertions(+)
 create mode 100644 .gitignore
 create mode 100644 .gitmodules
 create mode 100644 README.md
 create mode 100644 poetry.lock
 create mode 100644 pyproject.toml
```
