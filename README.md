# pumice
A poor mans obsidian.

Converts collection of markdown documents into html with browseable links.
Can be used locally or with a web server.

# Installing

```
python -m pip install pumice
```

# Usage

## Create a sample markdown collection
```python
pumice sample --folder example
```

## Convert markdown to html
```python
pumice generate --source-folder sample --destination-folder html
```

## Start webserver to serve html (file protocol does also works)
```python
pumice host --folder html --port 3000
```

# Sample

![Sample](https://github.com/styinx/pumice/blob/master/sample.png)


# Dependency
[3d-force-graph](https://github.com/vasturiano/3d-force-graph)
