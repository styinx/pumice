from argparse import ArgumentParser
from pathlib import Path
from random import randint
import shutil


DIR_ROOT = Path(__file__).parent
DIR_SRC = DIR_ROOT / 'sample'
lookup = []


def random_name(l: int = 10):
    chars = 'abcdefghijklmnopqrstuvwxyz'
    s = ''
    for i in range(l):
        s += chars[randint(0, len(chars) - 1)]
    return s


def create_folder(root: Path, base: Path, nested: int):
    global lookup
    folder = base / random_name()
    folder.mkdir(parents=True, exist_ok=True)
    files = [folder / (random_name() + '.md') for _ in range(randint(1, 3))]
    lookup += files
    for file in files:
        text = ''
        for _ in range(randint(1, 3)):
            link = lookup[randint(0, len(lookup) - 1)]
            rel_file = '../' * file.relative_to(root).as_posix().count('/')
            rel_link = rel_file + link.relative_to(root).as_posix()
            text += f'[{link.name}]({rel_link})\n\n'
        file.open('w').write(text)
    
    if nested > 0:
        create_folder(root, folder, nested - 1)


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('-d', '--destination', type=Path, default=DIR_SRC)

    args = parser.parse_args()

    if args.destination.exists():
        shutil.rmtree(args.destination)

    for i in range(randint(1, 3)):
        create_folder(args.destination, args.destination, randint(1, 3))
