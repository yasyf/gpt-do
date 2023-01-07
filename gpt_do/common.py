import sys


class Common:
    def __init__(self) -> None:
        self.debug = False

    def dprint(self, *args):
        if self.debug:
            print(*args, file=sys.stderr)
