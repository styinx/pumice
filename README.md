# pumice
A poor mans obsidian.

Converts collection of markdown documents into html with browseable links.

# Usage

## Create a sample markdown collection
```python
python create_sample.py --destination sample
```

## Convert markdown to html
```python
python generate.py --source sample --destination web --clear --theme themes/default.json
```

## Start webserver to serve html
```python
python start.py --source web --port 3000
```

# Sample
![Sample](https://github.com/styinx/pumice/blob/master/sample.png)
