import re
import json
from argparse import ArgumentParser, Namespace
from markdown import markdown, Markdown
from markdown.extensions import Extension
from markdown.extensions.tables import TableExtension
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
    else:
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

    REF_RE = r'\[([\.\/\w]+)\]\(([\.\/\w]+\.md)\)'

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

                    self._references.append({
                        'link': name,
                        'href': href
                    })

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


def write_template(env: Environment, dst: Path, template_name: str, name: str = '', **kwargs):
    if not name:
        # Remove the .jinja ending
        template_dst = dst / template_name[:template_name.rfind('.')]
    else:
        template_dst = dst / name

    template = env.get_template(template_name)
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
    if args.clear and args.destination.exists():
        logger.info(f'Removing folder {args.destination}')
        rmtree(args.destination)
        args.destination.mkdir()

    # Prepare generator environment
    env = Environment(loader=FileSystemLoader(DIR_TEMPLATES))
    env.filters['occurrences'] = lambda x, y : x.count(y)

    # Collect all markdown files in the source directory
    references = {}
    tree = {}
    for document in args.source.rglob('*.md'):
        content = document.open('r').read()

        # Normalize references and store them for each page
        references[document] = []
        html = markdown(content, extensions=[
            ReferenceExtension(args.destination, references[document]),
            TableExtension()
        ])

        # Resolve destination paths
        dest_path = args.destination / document.relative_to(args.source).parent
        dest_path.mkdir(parents=True, exist_ok=True)
        dest_file = (dest_path / document.stem).with_suffix('.html')
        rel_root = './' + '../' * dest_file.relative_to(args.destination).as_posix().count('/')

        # Page setup
        page = {'rel_root': rel_root, 'content': html}

        # Write the normalized pages to the destination directory
        write_template(env, dest_path, 'page.html.jinja', dest_file.name, page=page)

        # Add entry in the tree
        try:
            base = tree
            parents = iter(reversed(list(document.relative_to(args.source).parents)[:-1]))
            parent = next(parents)
            while parents:
                if parent.name not in base:
                    base[parent.name] = {}
                base = base[parent.name]
                parent = next(parents)
        except StopIteration:
            base[document.name] = str(dest_file.relative_to(args.destination))

    # Build the graph
    nodes, links = [], []

    for node in references.keys():
        nodes.append({
            'id': hash(node.as_posix()),       # Hashed file path
            'name': node.name,                 # Filename
            'group': hash(list(node.parents))  # Nesting count
        })
    
    root = args.source.parent
    for source, targets in references.items():
        for target in targets:
            relative_target = (source.parent / target['href']).resolve()
            links.append({
                'source': hash(source.as_posix()),
                'target': hash(relative_target.relative_to(root.absolute()).as_posix()),
            })

    graph = {'nodes': nodes, 'links': links}
    graph = json.dumps(graph, indent=2)

    # Load theme
    theme = json.load(args.theme.open('r'))

    # Write additional template files to the destination directory
    write_template(env, args.destination, 'Index.html.jinja', theme=theme, graph=graph, tree=tree)
    write_template(env, args.destination, 'style.css.jinja', theme=theme)

    # Copy resource files to the destination directory
    for path in DIR_RESOURCES.iterdir():
        dest = args.destination / path.name
        logger.info(f'Copy {path} to {dest}')
        copytree(src=path, dst=dest, dirs_exist_ok=True)


if __name__ == '__main__':
    main()