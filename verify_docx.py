import zipfile
import sys

docx_path = sys.argv[1] if len(sys.argv) > 1 else 'testdata/test_comment_fixed_v2.docx'

with zipfile.ZipFile(docx_path, 'r') as z:
    print('=== FILES ===')
    for f in z.namelist():
        print(f'  {f}')
    print()
    
    print('=== word/_rels/document.xml.rels ===')
    rels = z.read('word/_rels/document.xml.rels').decode('utf-8')
    print(rels)
    print()
    
    print('=== [Content_Types].xml (snippet) ===')
    ct = z.read('[Content_Types].xml').decode('utf-8')
    if 'comments' in ct:
        print('✅ comments.xml IS referenced')
        # Find the comments part
        import re
        match = re.search(r'<Override[^>]*comments[^>]*>', ct)
        if match:
            print(f'  {match.group(0)}')
    else:
        print('❌ comments.xml NOT referenced')
    print()
    
    print('=== commentReference in document.xml ===')
    doc_xml = z.read('word/document.xml').decode('utf-8')
    import re
    matches = re.findall(r'<w:r>.*?<w:commentReference[^/]*/>', doc_xml, re.DOTALL)
    for i, m in enumerate(matches):
        print(f'[{i}] {m[:150]}...')
        if '<w:rPr>' in m:
            print('    ✅ Has w:rPr')
        else:
            print('    ❌ Missing w:rPr')
