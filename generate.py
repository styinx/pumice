import re
import json
from argparse import ArgumentParser, Namespace
from markdown import markdown, Markdown
from markdown.extensions import Extension
from markdown.preprocessors import Preprocessor
from pathlib import Path
from logging import getLogger, basicConfig, DEBUG
from jinja2 import Environment, FileSystemLoader
from shutil import copytree, rmtree
from zlib import adler32


DIR_BASE = Path(__file__).parent
DIR_DST = DIR_BASE / 'dst'
DIR_SRC = DIR_BASE / 'src'
DIR_TEMPLATES = DIR_BASE / 'templates'
DIR_THEMES = DIR_BASE / 'themes'
DIR_RESOURCES = DIR_BASE / 'resources'

logger = getLogger()
basicConfig()


def hash(s) -> int:
    if isinstance(s, str):
        return adler32(bytes(s, encoding='utf-8'))
    return adler32(bytes(str(s), encoding='utf-8'))


class Mode:
    Full = 'full'
    Public = 'public'
    Private = 'private'

    Modes = Full, Public, Private


class ReferenceRename(Preprocessor):
    """
    Replaces md with html extension in reference structures: [...](...).
    """

    REF_RE = r'\[(\w+)\]\((\w+\.md)\)'

    def __init__(self, destination: Path, references: dict, md: Markdown = None) -> None:
        super().__init__(md)

        self._destination = destination
        self._references = references
    
    def run(self, lines: list) -> list:
        renamed_lines = []

        for line in lines:
            m = re.search(ReferenceRename.REF_RE, line)
            new_line = ''
            if m is None:
                new_line = line
            else:
                while m is not None:
                    name = m.group(1)
                    href = m.group(2)

                    path = self._destination / href
                    self._references.append((path, name))

                    new_line += line[:m.start(2)]
                    new_line += line[m.start(2):m.end(2)].replace('.md', '.html')
                    end = m.end(2)

                    m = re.search(ReferenceRename.REF_RE, line[m.end(2):])

                new_line += line[end:]

            renamed_lines.append(new_line)

        return renamed_lines


class ReferenceExtension(Extension):
    def __init__(self, destination: Path, references: list, **kwargs) -> None:
        super().__init__(**kwargs)

        self._destination = destination
        self._references = references

    def extendMarkdown(self, md: Markdown) -> None:
        md.preprocessors.register(ReferenceRename(self._destination, self._references, md), 'ref_rename', 170)


def write_template(env: Environment, dst: Path, src: str, **kwargs):
    template_dst = dst / src[:src.rfind('.')]  # Remove the .jinja ending
    template = env.get_template(src)
    template_dst.open('w+').write(template.render(**kwargs))
    logger.info(f'Write file: {template_dst}')


def main():
    parser = ArgumentParser(
        f'Looks for *.md files in the source folder and converts them into *.html files. '
        f'The converted files are written into the destination directory.')

    parser.add_argument('-c', '--clear', action='store_true')
    parser.add_argument('-d', '--destination', type=Path, default=DIR_DST)
    parser.add_argument('-m', '--mode', type=str, choices=Mode.Modes, default=Mode.Public)
    parser.add_argument('-s', '--source', type=Path, default=DIR_SRC)
    parser.add_argument('-t', '--theme', type=Path, default=DIR_THEMES / 'default.json')

    args = parser.parse_args()
    logger.debug(f'Arguments: {args}')

    # Clear the destination folder before writing
    if args.clear:
        logger.info(f'Removing folder {args.destination}')
        rmtree(args.destination)

    # Collect all markdown files in the source directory
    references = {}
    tree = {}
    for page in args.source.rglob('*.md'):
        content = page.open('r').read()

        # Normalize references and store them for each page
        node = page
        references[node] = []
        html = markdown(content, extensions=[ReferenceExtension(args.source, references[node])])

        # Write the normalized pages to the destination directory
        dest_path = args.destination / page.relative_to(args.source).parent
        dest_path.mkdir(parents=True, exist_ok=True)
        dest_file = (dest_path / page.stem).with_suffix('.html')
        dest_file.open('w+').write(html)
        logger.info(f'Write file: {dest_file}')

        # Add entry in the tree
        try:
            base = tree
            parents = iter(reversed(list(page.relative_to(args.source).parents)[:-1]))
            parent = next(parents)
            while parents:
                if parent.name not in base:
                    base[parent.name] = {}
                base = base[parent.name]
                parent = next(parents)
        except StopIteration:
            base[page.name] = str(dest_file.relative_to(args.destination))
    
    # Build the graph
    nodes = [{'id': hash(n), 'name': n.name, 'group': hash(list(n.parents))} for n in references.keys()]
    links = [{'source': hash(source), 'target': hash(target[0])} for source, targets in references.items() for target in targets]
    graph = {'nodes': nodes, 'links': links}

    # Load theme
    theme = json.load(args.theme.open('r'))

    # Page setup
    page = {'root': args.destination.as_posix()}

    # Write additional template files to the destination directory
    env = Environment(loader=FileSystemLoader(DIR_TEMPLATES))
    env.filters['occurrences'] = lambda x, y : x.count(y)
    write_template(env, args.destination, 'Documentation.html.jinja', page=page, graph=graph, tree=tree, theme=theme)
    write_template(env, args.destination, 'style.css.jinja', theme=theme)

    # Copy resource files to the destination directory
    for path in DIR_RESOURCES.iterdir():
        dest = args.destination / path.name
        logger.info(f'Copy {path} to {dest}')
        copytree(src=path, dst=dest, dirs_exist_ok=True)


if __name__ == '__main__':
    main()