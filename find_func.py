with open('streamlit_app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the end of _vantagem_banda_balsa function
idx = content.find('return "Refer')
if idx >= 0:
    # Find the end of the function (next def or end of file)
    next_func = content.find('\ndef _', idx + 1)
    if next_func < 0:
        next_func = len(content)
    print(f'End of function at {idx}, next func at {next_func}')
    print('Context:', repr(content[idx:idx+200]))