import pytest

from newxky.matching import KnowledgeIndex
from newxky.models import Question
from newxky.scroll_scan import QuestionFragments, ScrollReader, complete_match


def question(answers=('B',),stem='请判断本例中的正确内容（）'):
    return Question(1,'单选',stem,{'A':'这是完整的第一项内容','B':'这是完整的第二项内容',
                                  'C':'这是完整的第三项内容','D':'这是完整的第四项内容'},answers,(1,))


def frame(q, labels='ABCD', stem=True, order='CADB'):
    values={label:q.options[old] for label,old in zip('ABCD',order)}
    return (q.stem+'\n请选择一个答案\n' if stem else '')+'\n'.join(
        f'{label}. {values[label]}' for label in labels)


def feed(reader,text):
    return reader.feed(text,reader.index.lookup(text))


def test_two_frames_restore_actual_letters_and_require_all_choices():
    q=question()
    reader=ScrollReader(KnowledgeIndex([q]))
    first=feed(reader,frame(q,'AB'))
    assert first.direction==-1 and not first.match.answers
    last=feed(reader,frame(q,'CD',False))
    assert last.direction==0 and complete_match(last.match)
    assert last.match.answers==('D',) and '完整' in last.match.message


def test_even_a_visible_correct_choice_waits_until_all_options_are_read():
    q=question(('C',))
    reader=ScrollReader(KnowledgeIndex([q]))
    assert reader.index.lookup(frame(q,'AB')).status=='matched'
    assert feed(reader,frame(q,'AB')).direction==-1
    last=feed(reader,frame(q,'BCD',False))
    assert last.match.answers==('A',) and complete_match(last.match)


def test_starting_in_middle_first_reads_up_then_scans_down():
    q=question()
    reader=ScrollReader(KnowledgeIndex([q]))
    assert feed(reader,frame(q,'CD',False)).direction==1
    upper=frame(q,'AB')
    assert feed(reader,upper).direction==1
    assert feed(reader,upper).direction==1
    assert feed(reader,upper).direction==-1
    result=feed(reader,frame(q,'BCD',False))
    assert complete_match(result.match) and result.match.answers==('D',)


def test_long_stem_is_joined_from_observed_overlapping_rows():
    q=question(stem='根据本条例规定，负责监督管理的相关部门应当依法履行职责，下列说法正确的是（）')
    reader=ScrollReader(KnowledgeIndex([q]))
    upper=q.stem[:30]
    for _ in range(3):result=feed(reader,upper)
    assert result.direction==-1
    middle=q.stem[20:]+'\nA. '+q.options['C']+'\nB. '+q.options['A']
    assert feed(reader,middle).direction==-1
    last=feed(reader,frame(q,'CD',False))
    assert complete_match(last.match) and last.match.answers==('D',)


def test_wrapped_choice_continuation_is_merged_without_inventing_chars():
    q=question()
    q.options['C']='依法履行职责的相关部门需要公开办理程序并接受社会监督'
    fragments=QuestionFragments(KnowledgeIndex([q]))
    fragments.add(q.stem+'\nA. '+q.options['C'][:20])
    fragments.add(q.options['C'][10:]+'\nB. '+q.options['A']+
                  '\nC. '+q.options['D']+'\nD. '+q.options['B'])
    assert complete_match(fragments.lookup())
    assert fragments.lookup().answers==('D',)


def test_scroll_never_fills_missing_characters_from_bank():
    q=question()
    reader=ScrollReader(KnowledgeIndex([q]))
    feed(reader,frame(q,'AB'))
    damaged=frame(q,'CD',False).replace('第二项','另一个')
    for _ in range(3):last=feed(reader,damaged)
    assert last.direction==0 and last.match.status=='reference'
    assert '题库顺序' in last.match.message


def test_question_switch_discards_previously_collected_choices():
    old=question()
    new=Question(2,'单选','这是另一道题的实际完整题干（）',
                 {'A':'新内容甲','B':'新内容乙','C':'新内容丙','D':'新内容丁'},('C',),(2,))
    reader=ScrollReader(KnowledgeIndex([old,new]))
    feed(reader,frame(old,'AB'))
    feed(reader,frame(new,'AB',True,'ABCD'))
    last=feed(reader,frame(new,'CD',False,'ABCD'))
    assert complete_match(last.match) and last.match.question==new
    assert last.match.answers==('C',)


def test_switch_between_shared_stems_resets_collected_choices_and_scroll_budget():
    old = question()
    new = Question(2, '单选', old.stem, {
        'A': '新题第一项完整内容', 'B': '新题第二项完整内容',
        'C': '新题第三项完整内容', 'D': '新题第四项完整内容',
    }, ('C',), (2,))
    reader = ScrollReader(KnowledgeIndex([old, new]), max_steps=2)
    assert feed(reader, frame(old, 'AB')).direction == -1
    assert feed(reader, frame(old, 'B', False)).direction == -1
    # The stem is identical; the observed options identify a new bank entry.
    assert feed(reader, frame(new, 'AB', True, 'ABCD')).direction == -1
    assert reader.steps == 1
    last = feed(reader, frame(new, 'BCD', False, 'ABCD'))
    assert complete_match(last.match) and last.match.question is new
    assert last.match.answers == ('C',)


def test_a_conflicting_repeated_label_cannot_give_verified_answer():
    q=question()
    reader=ScrollReader(KnowledgeIndex([q]))
    feed(reader,frame(q,'AB'))
    changed=frame(q,'BCD',False).replace('第一项','错误项')
    for _ in range(3):last=feed(reader,changed)
    assert not complete_match(last.match)
    assert last.match.status=='reference'


def test_empty_unreadable_and_ambiguous_frames_do_not_start_scrolling():
    q=question()
    index=KnowledgeIndex([q])
    for text in ('', '未知题目', frame(q)+'\n'+frame(q)):
        assert not ScrollReader.needs_scan(text,index.lookup(text))


def test_no_stem_is_manufactured_when_only_lower_options_can_be_seen():
    q=question()
    reader=ScrollReader(KnowledgeIndex([q]))
    lower=frame(q,'CD',False)
    for _ in range(5):last=feed(reader,lower)
    assert last.direction==0 and last.match.status!='matched'


def test_scroll_budget_is_bounded_and_fallback_is_explicit():
    q=question()
    reader=ScrollReader(KnowledgeIndex([q]),max_steps=2)
    feed(reader,frame(q,'AB'))
    feed(reader,frame(q,'B',False))
    last=feed(reader,frame(q,'C',False))
    assert last.direction==0 and reader.steps==2
    assert last.match.status=='reference' and '题库顺序' in last.match.message


def test_complete_visible_question_needs_no_scroll():
    q=question()
    reader=ScrollReader(KnowledgeIndex([q]))
    result=feed(reader,frame(q))
    assert result.direction==0 and result.match.answers==('D',)


def test_unknown_window_text_with_an_incidental_letter_does_not_scroll():
    index=KnowledgeIndex([question()])
    text='工具列表和当前运行说明\nC. Plugins and desktop settings'
    assert not ScrollReader.needs_scan(text,index.lookup(text),index)


def test_next_option_tail_can_be_removed_only_when_it_is_seen_again():
    q=question()
    fragments=QuestionFragments(KnowledgeIndex([q]))
    fragments.add(frame(q,'A')+'\nB. '+q.options['A']+'\n'+q.options['D'][:8])
    fragments.add(frame(q,'BCD',False))
    assert complete_match(fragments.lookup())


def test_a_later_shorter_choice_cannot_silently_remove_a_negation():
    q=question()
    fragments=QuestionFragments(KnowledgeIndex([q]))
    fragments.add(frame(q,'AB').replace(q.options['A'],'不'+q.options['A']))
    fragments.add(frame(q,'BCD',False))
    assert not complete_match(fragments.lookup())


@pytest.mark.parametrize('changed', ['不应当','1.5','15'])
def test_scroll_does_not_erase_changed_stem_meaning(changed):
    q=question(stem='主管机关应当根据法定条件处理相关事项（）')
    reader=ScrollReader(KnowledgeIndex([q]))
    altered=frame(q,'AB').replace('应当',changed)
    for _ in range(5):last=feed(reader,altered)
    assert last.match.status!='matched'
