"""
Test script to verify Word comment creation works correctly.
Tests: comments.xml, document.xml.rels, [Content_Types].xml
"""
import os
import sys
import zipfile
import re

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_comment_injection():
    """Test the comment injection with the actual DocumentFiller code."""
    from docx import Document
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    
    # Create a test document
    doc = Document()
    para = doc.add_paragraph("テスト: コメント付きの段落です。")
    
    # Initialize comments storage
    comments_element = OxmlElement('w:comments')
    doc._comments_element = comments_element
    
    # Create comment reference in the document
    cid = "0"
    
    # commentRangeStart
    comment_range_start = OxmlElement('w:commentRangeStart')
    comment_range_start.set(qn('w:id'), cid)
    
    # commentRangeEnd
    comment_range_end = OxmlElement('w:commentRangeEnd')
    comment_range_end.set(qn('w:id'), cid)
    
    # commentReference run with proper rPr (THE FIX)
    comment_ref_run = OxmlElement('w:r')
    
    # Add rPr (run properties)
    run_props = OxmlElement('w:rPr')
    sz = OxmlElement('w:sz')
    sz.set(qn('w:val'), '16')
    run_props.append(sz)
    szCs = OxmlElement('w:szCs')
    szCs.set(qn('w:val'), '16')
    run_props.append(szCs)
    comment_ref_run.append(run_props)
    
    comment_ref = OxmlElement('w:commentReference')
    comment_ref.set(qn('w:id'), cid)
    comment_ref_run.append(comment_ref)
    
    # Insert into paragraph
    para_element = para._p
    pPr = para_element.find(qn('w:pPr'))
    if pPr is not None:
        pPr_index = list(para_element).index(pPr)
        para_element.insert(pPr_index + 1, comment_range_start)
    else:
        para_element.insert(0, comment_range_start)
    
    para_element.append(comment_range_end)
    para_element.append(comment_ref_run)
    
    # Create comment content
    comment = OxmlElement('w:comment')
    comment.set(qn('w:id'), cid)
    comment.set(qn('w:author'), 'Shadow Director AI')
    comment.set(qn('w:date'), '2026-02-01T22:00:00Z')
    comment.set(qn('w:initials'), 'SD')
    
    comment_para = OxmlElement('w:p')
    para_props = OxmlElement('w:pPr')
    comment_para.append(para_props)
    
    comment_run = OxmlElement('w:r')
    run_props2 = OxmlElement('w:rPr')
    run_props2_lang = OxmlElement('w:lang')
    run_props2_lang.set(qn('w:val'), 'ja-JP')
    run_props2.append(run_props2_lang)
    comment_run.append(run_props2)
    
    comment_text_elem = OxmlElement('w:t')
    comment_text_elem.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
    comment_text_elem.text = "【⚠️ 情報不足】これはテストコメントです。"
    comment_run.append(comment_text_elem)
    comment_para.append(comment_run)
    comment.append(comment_para)
    
    comments_element.append(comment)
    
    # Save document
    output_path = 'testdata/test_comment_fixed_v2.docx'
    doc.save(output_path)
    
    print(f"✅ Created base document: {output_path}")
    
    # Now use the actual DocumentFiller injection method
    from src.tools.document_filler import DocumentFiller
    filler = DocumentFiller()
    
    # Call injection
    filler._inject_comments_to_docx(output_path, comments_element)
    
    print("✅ Injected comments")
    
    # Verify
    verify_document(output_path)

def verify_document(docx_path):
    """Verify the document structure."""
    print(f"\n=== Verifying {docx_path} ===\n")
    
    errors = []
    
    with zipfile.ZipFile(docx_path, 'r') as z:
        # Check if comments.xml exists
        if 'word/comments.xml' in z.namelist():
            print("✅ word/comments.xml exists")
            comments_xml = z.read('word/comments.xml').decode('utf-8')
            if '<w:rPr>' in comments_xml:
                print("✅ comments.xml has w:rPr")
            else:
                errors.append("❌ comments.xml is missing w:rPr")
        else:
            errors.append("❌ word/comments.xml is MISSING!")
        
        # Check document.xml.rels
        rels_content = z.read('word/_rels/document.xml.rels').decode('utf-8')
        if 'comments.xml' in rels_content:
            print("✅ document.xml.rels has comments relationship")
        else:
            errors.append("❌ document.xml.rels is MISSING comments relationship!")
        
        # Check [Content_Types].xml
        content_types = z.read('[Content_Types].xml').decode('utf-8')
        if 'comments.xml' in content_types:
            print("✅ [Content_Types].xml has comments override")
        else:
            errors.append("❌ [Content_Types].xml is MISSING comments override!")
        
        # Check document.xml for proper commentReference structure
        doc_xml = z.read('word/document.xml').decode('utf-8')
        
        # Find commentReference runs
        matches = re.findall(r'<w:r[^>]*>.*?<w:commentReference[^/]*/>', doc_xml, re.DOTALL)
        print(f"\nFound {len(matches)} commentReference elements")
        
        for i, match in enumerate(matches[:3]):
            if '<w:rPr>' in match:
                print(f"✅ commentReference #{i} has w:rPr")
            else:
                errors.append(f"❌ commentReference #{i} is MISSING w:rPr!")
    
    print("\n" + "="*50)
    if errors:
        print("ERRORS FOUND:")
        for e in errors:
            print(f"  {e}")
        return False
    else:
        print("ALL CHECKS PASSED! ✅")
        return True

if __name__ == '__main__':
    test_comment_injection()
