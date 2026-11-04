"""Bounded real-model workflow, executable only for a private platform test worker."""
import json
import os
from pathlib import Path
import zipfile
import io

from le_platform.worker import prepare,model_client


def main():
    if os.environ.get('LE_ACCEPTANCE_TEST')!='1' or os.geteuid()==0:raise RuntimeError('Dedicated test worker required')
    prepare()
    from sqlmodel import Session,select
    from ktem.db.engine import engine
    from learning_ext.bootstrap import init_learning_ext
    from learning_ext.path_generator.service import generate_roadmap,save_roadmap
    from learning_ext.db.models import LearningProject,KnowledgeNode,Card,Quiz,QuizQuestion
    from learning_ext.fsrs_review.service import generate_cards_from_node,review_card,RATING_GOOD
    from learning_ext.quiz.service import generate_quiz,grade_answer
    from learning_ext.notes.service import save_note
    from learning_ext.exporter.service import export_markdown,export_anki_apkg
    from le_platform.embeddings import LocalEmbeddings
    init_learning_ext()
    path=Path(os.environ['LE_WORKER_ROOT'])/'data/platform-acceptance.json'
    result=json.loads(path.read_text()) if path.exists() else {'passed':False,'checks':[]}
    def save():path.write_text(json.dumps(result,indent=2));path.chmod(0o600)
    def checked(value):
        if value not in result['checks']:result['checks'].append(value)
        save()
    try:
        if 'real gateway reply' not in result['checks']:
            with model_client() as client:
                reply=client.chat.completions.create(model='deepseek-flash',messages=[{'role':'user','content':'平台上线验收。只回复 LEARN_UPGRADE_OK。'}],
                    max_tokens=128,extra_body={'thinking':{'type':'disabled'}})
            assert 'LEARN_UPGRADE_OK' in reply.choices[0].message.content
            checked('real gateway reply')
        with Session(engine) as session:
            project=session.exec(select(LearningProject).where(LearningProject.title=='平台上线验收课程')).first()
            if project is None:
                roadmap=generate_roadmap('Python读取与保存CSV，仅三个入门知识点','已有Python环境','30分钟内读取并保存一张CSV表格，最多3个知识点',2,model_name='deepseek-flash')
                assert isinstance(roadmap.get('nodes'),list) and 0<len(roadmap['nodes'])<=12
                project=save_roadmap(session,'default','Python读取CSV','有Python环境','读取与保存CSV',2,roadmap,title='平台上线验收课程')
            nodes=session.exec(select(KnowledgeNode).where(KnowledgeNode.project_id==project.id)).all()
            assert nodes;result.update(projectId=project.id,nodes=len(nodes));checked('actual generated roadmap persisted')
            note=save_note(session,nodes[0].id,project.id,'平台验收：CSV读取结果需要检查列名与编码。')
            assert note.content;checked('note persisted')
            cards=session.exec(select(Card).where(Card.project_id==project.id)).all()
            if not cards:cards=generate_cards_from_node(session,nodes[0].id,'default',nodes[0].description,count=2,model_name='deepseek-flash')
            assert cards;result['cards']=len(cards);checked('actual model-generated review cards persisted')
            if 'FSRS review recorded' not in result['checks']:
                card=review_card(session,cards[0].id,RATING_GOOD)
                assert card.next_review is not None;checked('FSRS review recorded')
            quiz=session.exec(select(Quiz).where(Quiz.project_id==project.id)).first()
            if quiz is None:quiz=generate_quiz(session,'default',[nodes[0].id],project_id=project.id,count=1,qtype='choice',model_name='deepseek-flash')
            questions=session.exec(select(QuizQuestion).where(QuizQuestion.quiz_id==quiz.id)).all()
            assert questions;checked('actual generated quiz persisted')
            attempt=grade_answer(session,questions[0].id,questions[0].answer,model_name='deepseek-flash')
            assert attempt.is_correct;checked('quiz answer graded and recorded')
            markdown=export_markdown(session,project.id);assert '平台上线验收课程' in markdown
            archive=export_anki_apkg(session,project.id)
            with zipfile.ZipFile(io.BytesIO(archive)) as packed:assert any(name.endswith('.txt') for name in packed.namelist())
            (Path(os.environ['LE_WORKER_ROOT'])/'workspace/acceptance-notes.md').write_text(markdown)
            result['exportBytes']=len(markdown.encode());checked('Markdown and Anki-compatible exports')
        vectors=LocalEmbeddings(model_name='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2').invoke(['CSV读写学习资料','学习资料检索'])
        assert len(vectors)==2 and all(len(item.embedding)==384 for item in vectors)
        checked('real local multilingual embeddings')
        result['passed']=True;save()
    except Exception as error:
        result.update(passed=False,errorType=type(error).__name__,error=str(error)[:600]);save();raise
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
