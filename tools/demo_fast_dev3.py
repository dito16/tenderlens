"""FD3 synthetic integration: PDF -> import -> analysis -> corrections -> revision -> export.

All actions are against fresh demo-local data, not real human reviews or G4.
"""
import argparse
import json
from pathlib import Path
import pymupdf
from tender_screen.storage import LocalStore,_file_sha


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--data-root',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    src=Path(__file__).resolve().parents[1]/'examples'/'fast_dev3_conflict_pack'
    with LocalStore(a.data_root) as store:
        store.project('FAST DEV 3 DEMO')
        initial=store.import_pdfs('FAST DEV 3 DEMO',sorted(src.glob('*.pdf')))
        repeat=store.import_pdfs('FAST DEV 3 DEMO',sorted(src.glob('*.pdf')))
        first=store.analyze_project('FAST DEV 3 DEMO')
        assert initial['count_added']==3 and repeat['count_existing']==3
        questions=store.questions(first['run_id'])
        kinds={q['payload']['kind'] for q in questions}
        required={'opposing_sro_wording','opposing_advance_wording','different_payment_delay_wording'}
        assert required.issubset(kinds),(required,kinds)
        items=store.claims(first['run_id']);assert items
        claim=items[0]
        store.review_claim(claim['id'],'DEMO_TEST_CORRECTION_NOT_HUMAN_VERIFIED',
                           'Synthetic test only: evidence remains unchanged',actor='demo_test')
        store.resolve_question(questions[0]['local_question_id'],
                 'DEMO TEST ONLY: reviewer would need to inspect source revisions',actor='demo_test')
        assert store.questions(first['run_id'])[0]['status']=='resolved_by_user'
        export1=store.export(first['run_id'],a.out/'exports')
        source=src/'03_contract.pdf';changed=a.out/'locally_changed_revision'/'03_contract.pdf'
        changed.parent.mkdir(parents=True,exist_ok=True)
        with pymupdf.open(source) as document:
            page=document.new_page()
            page.insert_text((30,35),'Synthetic local revision: changed PDF hash only.')
            document.save(changed)
        add=store.import_pdfs('FAST DEV 3 DEMO',[changed],{changed.name:{'revision':'local-v2','effective':'unknown'}})
        second=store.analyze_project('FAST DEV 3 DEMO')
        diff=store.compare_runs(first['run_id'],second['run_id'])
        assert [x['filename'] for x in diff['document_changes'] if x['status']=='changed']==['03_contract.pdf']
        export2=store.export(second['run_id'],a.out/'exports')
        summary={'schema':'tenderlens.fast_dev3.demo.v1','synthetic_only':True,
            'input_pdfs':3,'imported':initial['count_added'],'deduped':repeat['count_existing'],
            'first_run_id':first['run_id'],'second_run_id':second['run_id'],
            'detected_review_questions':len(questions),
            'detected_kinds':sorted(kinds),
            'attachment_questions':len(store._run_view(first['run_id'])['machine_result']['fast_dev3']['comparison']['attachment_questions']),
            'first_run_claims':len(items),'manual_demo_review_id':claim['id'],
            'revision_diff':diff['document_changes'],
            'export_dirs':[str(export1),str(export2)],
            'warnings':['demo_test_only_not_a_human_review','no_gold_holdout','no_legal_verdict']}
    (a.out/'FD3_DEMO_SUMMARY.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    with LocalStore(a.data_root) as reopened:
        assert len(reopened.runs('FAST DEV 3 DEMO'))==2
        assert reopened._run_view(first['run_id'])['reviewed_claims'][0]['origin']=='human_review'
        assert reopened.questions(first['run_id'])[0]['status']=='resolved_by_user'
        assert reopened.documents('FAST DEV 3 DEMO')[0]['sha256']
    print(f"FD3_DEMO_PASS: imports=3, deduped=3, conflicts={len(questions)}, revisions=2, claims={len(items)}")
    print('RESULT=',a.out/'FD3_DEMO_SUMMARY.json')
if __name__=='__main__':main()
