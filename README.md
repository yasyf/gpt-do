# `gpt-do`

This is a handy-dandy CLI for when you don't know wtf to do.

Instead of furiously grepping through man pages, simply use `do` (or `ddo` if on `bash`/`zsh`), and have GPT-3 do all the magic for you.

Check out the blog post [here](https://musings.yasyf.com/never-write-a-bash-command-again-with-gpt-3/).

## Demo

Click to play:

[![asciicast](https://asciinema.org/a/oXRkVfVsxvUFq4SFjrstgsZck.png)](https://asciinema.org/a/oXRkVfVsxvUFq4SFjrstgsZck?i=0.5&autoplay=1)

## Installation

We recommend using [`pipx`](https://pypa.github.io/pipx/):

```console
$ pipx install gpt-do
$ which do
~/.local/bin/do
```

However you can also use `brew`:

```console
$ brew install yasyf/do/do
$ which do
/opt/homebrew/bin/do
```

Or `pip`:

```console
$ pip install gpt-do
$ which do
~/.asdf/installs/python/3.11.0/bin/do
```

## Usage

**n.b.** If you're on `bash` or `zsh`, `do` is a reserved keyword, so you'll have to use the alias `ddo`.

**n.b.** The default model used is **GPT-3**. Please ensure you have sufficient credits in your OpenAI account to use it.

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
