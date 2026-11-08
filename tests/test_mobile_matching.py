import pytest

from newxky.matching import KnowledgeIndex
from newxky.models import Question


@pytest.mark.parametrize('hint', ['请选择一个答案', '请选择所有正确选项', '请选择一项正确答案'])
def test_mobile_instructions_do_not_change_the_stem_or_screen_letters(hint):
    question=Question(1,'单选','必须坚持科技是第一生产力、人才是第一资源、（）是第一动力。',
                      {'A':'教育','B':'发展','C':'改革','D':'创新'},('D',),(1,))
    text=question.stem+'\n'+hint+'\nA 创新\nB 教育\nC 发展\nD 改革'
    result=KnowledgeIndex([question]).lookup(text)
    assert result.status=='matched' and result.answers==('A',)


def test_a_choice_that_is_also_a_judgment_stem_is_not_a_second_question():
    question=Question(1,'单选','以下关于相关教育的说法哪一项错误（）',
                      {'A':'教育是公民的一项权利和义务','B':'接受教育是一项义务而非权利',
                       'C':'应当普及教育','D':'依法开展教育'},('B',),(1,))
    judgment=Question(2,'判断',question.options['A']+'。（）',
                      {'A':'正确','B':'错误'},('A',),(2,))
    result=KnowledgeIndex([question,judgment]).lookup(
        question.stem+'\n请选择一个答案\n'+
        '\n'.join(f'{label} {value}' for label,value in question.options.items()))
    assert result.status=='matched' and result.answers==('B',)


def test_instruction_like_words_inside_prose_are_kept():
    question=Question(1,'单选','请选择一个答案并说明原因这一要求是否正确（）',
                      {'A':'是','B':'否'},('A',),(1,))
    result=KnowledgeIndex([question]).lookup(question.stem+'\nA 是\nB 否')
    assert result.status=='matched'


@pytest.mark.parametrize('number,order,expected',[(618,'ABDC',('B','C','D')),
                                                 (483,'DBAC',('A','B','D')),
                                                 (33,'DABC',('A',))])
def test_reported_mobile_cards_use_actual_page_order(number,order,expected):
    from pathlib import Path
    from newxky.bank import read_bank
    bank=read_bank(Path(__file__).resolve().parents[1]/'题库/default-bank.json')
    question=next(question for question in bank.questions if question.number==number)
    text=question.stem+'\n请选择所有正确选项\n'+'\n'.join(
        f'{label} {question.options[old]}' for label,old in zip('ABCD',order))
    match=KnowledgeIndex(bank.questions).lookup(text)
    assert match.status=='matched' and match.answers==expected


def test_type_and_decorative_number_on_separate_lines_are_removed():
    question=Question(1,'单选','本题的实际题干（）',{'A':'甲','B':'乙'},('A',),(1,))
    match=KnowledgeIndex([question]).lookup('单选题\n01\n'+question.stem+'\nA 甲\nB 乙')
    assert match.status=='matched'
