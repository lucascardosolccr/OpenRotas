import re

with open('streamlit_app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the function
idx = content.find('def _vantagem_banda_balsa')
if idx >= 0:
    next_func = content.find('\ndef _', idx + 1)
    if next_func < 0:
        next_func = len(content)
    
    print(f'Found at {idx}, next func at {next_func}')
    
    # Check if it has try block
    func_content = content[idx:next_func]
    if 'try:' not in content[idx:idx+200]:
        print('Missing try block, fixing...')
        
        # Find exact boundaries
        func_start = idx
        func_end = content.find('\ndef _', idx + 1)
        if func_end < 0:
            func_end = len(content)
        
        old_func = content[idx:func_end]
        
        new_func = '''def _vantagem_banda_balsa(da, dr, balsa_app, balsa_ref, margem, fallback="Empate"):
    """Vantagem (app × referência) sob a política ÚNICA §6/§7 — substitui o peso fixo _PEN_BALSA_KM
    no comparador. Regras:
      • mesmo status → vence a menor distância (empate técnico respeitando 'margem');
      • um lado com balsa: a RODOVIÁRIA razoável vence; a travessia só vence quando a rodovia é
        desvio desproporcional (não razoável) — São José do Norte continua ganhando com a balsa;
      • nunca tempo/custo invertem a menor rota. PURA/defensiva."""
    try:
        _a = _num_seguro(da); _b = _num_seguro(dr)
        if _a is None or _b is None:
            return fallback
        _ba, _br = bool(balsa_app), bool(balsa_ref)
        if _ba == _br:
            if abs(_a - _b) < max(1.0, float(margem)):
                return "Empate"
            return "Aplicação" if _a < _b else "Referência"
        if _ba and not _br:
            if _rota_sem_balsa_razoavel(_a, _b):
                return "Referência"
            if abs(_a - _b) < max(1.0, float(margem)):
                return "Empate"
            return "Aplicação"
        if _br and not _ba:
            if _rota_sem_balsa_razoavel(_b, _a):
                return "Aplicação"
            if abs(_a - _b) < max(1.0, float(margem)):
                return "Empate"
            return "Referência"
    except Exception:
        return fallback
'''
        
        # Replace
        start_idx = content.find('def _vantagem_banda_balsa')
        func_end = content.find('\ndef _', idx + 1)
        if func_end < 0:
            func_end = len(content)
        
        new_content = content[:content.find('def _vantagem_banda_balsa')] + new_func + content[content.find('\ndef _', idx + 1):]
        
        with open('streamlit_app.py', 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        print('Fixed!')