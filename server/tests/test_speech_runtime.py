import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app import config
from app.brain.claude_cli import ClaudeCLI, IDLE_RESET_S
from app.voice.grammar import self_reference


@pytest.mark.parametrize('text,gender,expected', [
    ('עכשיו אני שואל: האם אתה מוכן?', 'neutral', 'עכשיו השאלה שלי היא: האם אתה מוכן?'),
    ('אני שואלת אותך אם את מוכנה.', 'neutral', 'השאלה שלי היא אם את מוכנה.'),
    ('אני שואל: את מוכנה?', 'feminine', 'אני שואלת: את מוכנה?'),
    ('אני שואלת: אתה מוכן?', 'masculine', 'אני שואל: אתה מוכן?'),
    ('אני לא שואל אם את מוכנה.', 'neutral', 'אני לא שואל אם את מוכנה.'),
    ('אני שואל ספר מהספרייה.', 'neutral', 'אני שואל ספר מהספרייה.'),
    ('הוא אמר ״אני שואל: האם אתה מוכן?״', 'neutral', 'הוא אמר ״אני שואל: האם אתה מוכן?״'),
    ('"אני שואל: את מוכנה?"', 'neutral', '"אני שואל: את מוכנה?"'),
    ('בחרת מטרייה. עכשיו אני שואל: האם את מוכנה?', 'neutral', 'בחרת מטרייה. עכשיו השאלה שלי היא: האם את מוכנה?'),
    ('אני זוכר את זה לשיחה הזאת.', 'neutral', 'זכרתי את זה לשיחה הזאת.'),
    ('אני זוכרת מה בחרת.', 'neutral', 'זכרתי מה בחרת.'),
    ('היא אמרה ״אני זוכרת מה בחרת״.', 'neutral', 'היא אמרה ״אני זוכרת מה בחרת״.'),
    ('אני לא זוכר את זה.', 'neutral', 'אני לא זוכר את זה.'),
    ('אני זוכרת את זה.', 'feminine', 'אני זוכרת את זה.'),
])
def test_self_reference_preserves_meaning_and_user_address(text, gender, expected):
    assert self_reference(text, gender) == expected


def test_prepare_reuses_process_and_updates_preferences_without_history_reset(monkeypatch, tmp_path):
    from app.brain import claude_cli
    monkeypatch.setattr(config, 'CLAUDE_WORKDIR', str(tmp_path))
    monkeypatch.setattr(config, 'USER_ADDRESS', 'masculine')
    monkeypatch.setattr(config, 'ASSISTANT_GENDER', 'neutral')

    async def check():
        writes=[]
        class Input:
            def write(self, value): writes.append(json.loads(value))
            async def drain(self): pass
        output=asyncio.StreamReader()
        proc=SimpleNamespace(returncode=None,pid=123,stdin=Input(),stdout=output,stderr=None)
        spawn=AsyncMock(return_value=proc)
        monkeypatch.setattr(asyncio, 'create_subprocess_exec', spawn)
        brain=ClaudeCLI()
        await brain.prepare()
        assert not writes and brain.turns==0
        assert brain.last>0
        async def turn():
            output.feed_data(b'{"type":"stream_event","event":{"type":"content_block_delta","delta":{"type":"text_delta","text":"ok"}}}\n{"type":"result","subtype":"success"}\n')
            return ''.join([s async for s in brain.ask('question','remember the purple umbrella')])
        assert await turn()=='ok'
        monkeypatch.setattr(config,'USER_ADDRESS','feminine')
        monkeypatch.setattr(config,'ASSISTANT_GENDER','feminine')
        assert await turn()=='ok'
        assert spawn.await_count==1 and brain.turns==2
        assert 'את, תרצי, יכולה' in writes[-1]['message']['content']
        assert 'אני מוכנה, אני יכולה' in writes[-1]['message']['content']
        assert 'remember the purple umbrella' in writes[-1]['message']['content']
        args=spawn.call_args.args
        system=args[args.index('--system-prompt')+1]
        assert 'פנה למשתמש בלשון זכר יחיד' not in system
        # Idle expiry still resets; preparation must not disable bounded histories.
        async def reset(): brain.proc=None
        brain.reset=AsyncMock(side_effect=reset)
        brain.last=claude_cli.time.time()-IDLE_RESET_S-1
        await brain.prepare()
        brain.reset.assert_awaited_once()
        assert spawn.await_count==2
    asyncio.run(check())
