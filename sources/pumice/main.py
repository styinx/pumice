from argparse import ArgumentParser, Namespace
from concurrent.futures import ThreadPoolExecutor
from http.server import HTTPServer, SimpleHTTPRequestHandler
from importlib import util
from itertools import chain
from jinja2 import Environment, FileSystemLoader
from json import dumps
from multiprocessing import Queue, cpu_count
from os import path as OsPath
from pathlib import Path
from queue import Empty as QueueEmpty
from random import choice, randint
from re import compile, sub
from shutil import copytree, rmtree
from string import ascii_lowercase
from sys import exit
from threading import Lock
from webbrowser import open as open_browser

import sys

from markdown_it import MarkdownIt

from pumice.util.logger import get_logger, LogLevel

DocumentLinks = dict[Path, list[Path]]

DIR_BASE = Path(__file__).parent.parent
DIR_RESOURCES = DIR_BASE / 'resources'
DIR_TEMPLATES = DIR_BASE / 'templates'
DIR_THEMES = DIR_BASE / 'themes'

RE_MD_FILE_EXTENSION = compile(r'\.md$')

# Document subtrees of outgoing links
DOCUMENT_LINKS: DocumentLinks = {}

lock = Lock()

logger = get_logger('pumice')


class Visibility:
    Public = 'public'
    Private = 'private'

    Choices = [Public, Private]


def process_outgoing_links(self, tokens, idx, options, env):
    """
    Replaces md with html extension in reference structures: [...](...).
    In addition, outgoing document links are collected.
    """

    token = tokens[idx]
    html_file: Path = env.get('current_file')
    base: Path = env.get('base_dir')

    # Replace the link extension
    token.attrs['href'] = sub(RE_MD_FILE_EXTENSION, '.html', token.attrs['href'])

    if html_file and base:
        rel_path = base / html_file.parent / Path(token.attrs['href'])
        link = rel_path.resolve().relative_to(base.resolve())
        with lock:
            DOCUMENT_LINKS[html_file].append(link)

    return self.renderToken(tokens, idx, options, env)


def process_md_file(md_files: Queue, md_processor: MarkdownIt, jinja_env: Environment, args: Namespace) -> None:
    """
    Converts a markdown file into html and writes it to the destination folder.
    """

    while md_files.qsize() > 0:
        try:
            md_file = md_files.get_nowait()

            logger.debug(md_file)

            if args.mode == Visibility.Public and md_file.as_posix().find(Visibility.Private) >= 0:
                continue

            # Prepare the destination folder.
            folder = md_file.parent.relative_to(args.source_folder)
            destination_folder = args.destination_folder / folder
            destination_folder.mkdir(parents=True, exist_ok=True)

            # Determine file name
            html_file_name = sub(RE_MD_FILE_EXTENSION, '.html', md_file.name)
            html_file = Path(destination_folder / html_file_name)

            # Record links
            with lock:
                DOCUMENT_LINKS[html_file] = []

            # Convert markdown to html.
            md_env = {'current_file': html_file, 'base_dir': args.destination_folder}
            md_content = open(md_file, 'r', encoding='utf-8').read()
            html_content = md_processor.render(md_content, env=md_env).strip()

            # Write html content to file based on the template.
            page_template = jinja_env.get_template('page.html.jinja')
            html_file.open('w+').write(
                page_template.render(
                    page={
                        'content': html_content,
                        'rel_root': Path(OsPath.relpath(args.destination_folder, html_file.parent))
                    }
                )
            )

        except QueueEmpty:
            break

        except Exception as e:
            logger.error(e)


def build_graph(link_list: DocumentLinks, args: Namespace) -> dict:
    nodes, links = [], []

    html_files = set([x for x in chain(link_list.keys(), *link_list.values())])
    incoming_links = {file: sum(file in targets for targets in link_list.values()) for file in html_files}

    for html_file in html_files:
        nodes.append({
            'id': hash(html_file.as_posix()),  # Hashed file path
            'size': incoming_links.get(html_file, 1),  # Incoming links count
            'name': html_file.name,  # Filename
            'group': len(list(html_file.parents)),  # Nesting count
            'src': './' + html_file.relative_to(args.destination_folder).as_posix()
        })

    for source_node, target_nodes in link_list.items():
        for target_node in target_nodes:
            links.append({
                'source': hash(source_node.as_posix()),
                'target': hash(target_node.as_posix()),
                'weight': (len(link_list[source_node]) + len(link_list[target_node])) // 2
            })

    return {'nodes': nodes, 'links': links}


def build_tree(root_path: Path) -> dict:
    tree = {}
    for path in root_path.rglob('*'):
        parts = path.relative_to(root_path).parts
        current_level = tree
        for part in parts[:-1]:  # Traverse the path, excluding the last part
            current_level = current_level.setdefault(part, {})
        current_level[parts[-1]] = path.relative_to(root_path).as_posix() if path.is_file() else {}
    return tree


def generate(args: Namespace):
    """
    Collects markdown files from a folder and saves the converted html content
    to a destination folder.
    """

    # Cleanup outdated files from previous runs.
    if args.destination_folder.exists():
        rmtree(args.destination_folder)
    args.destination_folder.mkdir(parents=True, exist_ok=True)

    # Processor for markdown files.
    md_processor = MarkdownIt('commonmark')
    md_processor.add_render_rule('link_open', process_outgoing_links)

    # Jinja environment for templates files.
    jinja_env = Environment(loader=FileSystemLoader(args.jinja_folder), keep_trailing_newline=False)

    # Collect all markdown files from the source directory.
    logger.info('Collecting markdown files...')
    file_queue = Queue()
    for md_file in list(args.source_folder.rglob('*.md')):
        file_queue.put(md_file)
    logger.info('Done')

    # Process markdown files in parallel.
    logger.info('Processing markdown files...')
    with ThreadPoolExecutor(max_workers=cpu_count() - 1) as executor:
        for _ in range(cpu_count() - 1):
            executor.submit(process_md_file, file_queue, md_processor, jinja_env, args)
    logger.info('Done')

    logger.info('Building document graph...')
    document_graph = dumps(build_graph(DOCUMENT_LINKS, args), indent=2)
    logger.info('Done')

    logger.info('Building document tree...')
    document_tree = build_tree(args.destination_folder)
    logger.info('Done')

    spec = util.spec_from_file_location(args.theme.stem, args.theme)
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, "theme"):
        raise RuntimeError("Script must define a run() function")

    theme = module.theme()

    logger.debug('Theme:')
    logger.debug(theme)

    # Write index file.
    logger.info('Writing template base files...')
    index_template = jinja_env.get_template('index.html.jinja')
    index_file = args.destination_folder / 'index.html'
    index_file.open(
        'w+', encoding='utf-8'
    ).write(
        index_template.render(
            config={'name': args.name if args.name else args.source_folder.name},
            graph=document_graph,
            theme=theme,
            tree=document_tree
        )
    )

    # Write style file.
    style_template = jinja_env.get_template('style.css.jinja')
    style_file = args.destination_folder / 'style.css'
    style_file.open('w+', encoding='utf-8').write(style_template.render(theme=theme))
    logger.info('Done')

    # Copy resource folder
    logger.info('Copying resources...')
    resource_folder = args.destination_folder / 'resources'
    copytree(args.resource_folder, resource_folder)
    logger.info('Done')


def host(args: Namespace):

    def get_handler(folder: Path):

        class Handler(SimpleHTTPRequestHandler):

            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=folder, **kwargs)

        return Handler

    logger.info(f'{args.folder} {args.port}')
    server = HTTPServer(('', args.port), get_handler(args.folder))
    open_browser(f'http://localhost:{args.port}')

    try:
        logger.info(f'Starting web server from {args.folder} at {args.port}...')
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info('Shutdown received...')
        server.server_close()


def sample(args: Namespace):
    files = []

    # Cleanup outdated files from previous runs.
    logger.info(f'Cleanup folder "{args.folder}"...')
    if args.folder.exists():
        rmtree(args.folder)
    args.folder.mkdir(parents=True, exist_ok=True)
    logger.info('Done')

    nesting_depth = randint(*args.nesting_depth)

    def _random_name():
        return ''.join(choice(ascii_lowercase) for _ in range(randint(5, 10)))

    def _populate(folder: Path, depth: int):
        if depth == nesting_depth:
            return

        documents = randint(*args.document_count)
        links = randint(*args.link_count)
        subfolders = randint(*args.subfolder_count)

        logger.info(f'- {folder} [{depth=}, {documents=}, {links=}, {subfolders=}]')

        for _ in range(documents):
            file_path = folder / f'{_random_name()}.md'
            fp = file_path.open('w')
            fp.write(f'# {file_path.name}\n')
            if files:
                for _ in range(links):
                    random_link = choice(files)
                    rel_path = Path(OsPath.relpath(random_link, file_path.parent))
                    fp.write(f'[{rel_path.name}]({rel_path.as_posix()})\n')
            files.append(file_path)

        for _ in range(subfolders):
            sub_folder_name = folder / _random_name()
            sub_folder_name.mkdir(parents=True, exist_ok=True)
            _populate(sub_folder_name, depth + 1)

    logger.info('Create sample...')
    _populate(args.folder, 0)
    logger.info('Done')


def create_parser():
    """
    Creates the argument parser for this program.
    """
    parser = ArgumentParser(
        f'Looks for *.md files in the source folder and converts them into *.html files. '
        f'The converted files are written into the destination directory.'
    )
    parser.add_argument('-l', '--log-level', type=str, choices=LogLevel.Levels, default=LogLevel.Info)

    sub_parsers = parser.add_subparsers(dest='command')

    generate = sub_parsers.add_parser(
        'generate',
        help=f'Looks for *.md files in the source folder and converts them into *.html files. '
        f'The converted files are written into the destination directory.'
    )
    generate.add_argument('-d', '--destination-folder', type=Path, required=True)
    generate.add_argument('-j', '--jinja-folder', type=Path, default=DIR_TEMPLATES)
    generate.add_argument('-n', '--name', type=str)
    generate.add_argument('-m', '--mode', type=str, choices=Visibility.Choices, default=Visibility.Public)
    generate.add_argument('-r', '--resource-folder', type=Path, default=DIR_RESOURCES)
    generate.add_argument('-s', '--source-folder', type=Path, required=True)
    generate.add_argument('-t', '--theme', type=Path, default=DIR_THEMES / 'default.py')

    host = sub_parsers.add_parser('host', help='Starts an HTTP server.')
    host.add_argument('-f', '--folder', type=Path, required=True)
    host.add_argument('-p', '--port', type=int, default=8000)

    sample = sub_parsers.add_parser('sample', help='Creates sample files.')
    sample.add_argument('-d', '--document-count', type=tuple, default=(2, 4))
    sample.add_argument('-f', '--folder', type=Path, required=True)
    sample.add_argument('-l', '--link-count', type=tuple, default=(1, 5))
    sample.add_argument('-n', '--nesting-depth', type=tuple, default=(2, 4))
    sample.add_argument('-s', '--subfolder-count', type=tuple, default=(1, 5))

    return parser


def main(argv: list[str] = sys.argv[1:]) -> int:
    parser = create_parser()

    args = parser.parse_args(argv)

    logger.setLevel(args.log_level.upper())

    if args.command == 'generate':
        generate(args)

    elif args.command == 'host':
        host(args)

    elif args.command == 'sample':
        sample(args)

    else:
        parser.print_help()

    return 0


if __name__ == '__main__':
    exit(main())
