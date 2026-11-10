"""Validate neural-reader boundaries without model downloads or API calls.

These are schema/runtime contract tests. They do not measure the pretrained
model's ability to count an actual worksheet; that needs separate image runs.
"""
import copy
import json
import os
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from lesson_video.local_vision import (LocalVisionError, MAX_TOKENS, MODEL_ID,
                                      _loaded_model, parse_model_response,
                                      read_local_vision, resolve_model_path,
                                      validate_interpretation)


def _payload(**updates):
    value = {'status': 'ready', 'exercise_count': 1, 'task_type': 'addition',
             'a': 5, 'b': 2, 'unknown_operand': False, 'printed_answer': None,
             'object_label': 'popsicle', 'object_label_plural': 'popsicles',
             'shape': None, 'shape_task': None,
             'task_text': 'Two pictured groups separated by a plus sign and an empty answer box.',
             'uncertainty': False, 'reason': 'The two complete groups are clear and separate.'}
    value.update(updates)
    return value


class LocalVisionValidationTests(unittest.TestCase):
    def test_computes_arithmetic_in_python_without_a_model_answer(self):
        original = _payload()
        before = copy.deepcopy(original)
        result = validate_interpretation(original)
        self.assertEqual((result['spec']['a'], result['spec']['b'], result['spec']['answer']), (5, 2, 7))
        self.assertEqual(result['question'], 'What is 5 + 2?')
        self.assertEqual(original, before)
        self.assertEqual(result['spec']['object_label'], 'popsicle')
        self.assertTrue(any('dots' in step['text'] for step in result['spec']['steps']))
        self.assertEqual(result['model_interpretation']['object_label'], 'popsicle')

    def test_all_supported_operand_pairs_keep_deterministic_answers(self):
        for a in range(11):
            for b in range(11):
                for kind in ('addition', 'subtraction'):
                    valid = a+b <= 10 if kind == 'addition' else b <= a
                    with self.subTest(a=a, b=b, kind=kind):
                        payload = _payload(task_type=kind, a=a, b=b)
                        if valid:
                            answer = validate_interpretation(payload)['spec']['answer']
                            self.assertEqual(answer, a+b if kind == 'addition' else a-b)
                        else:
                            with self.assertRaises(LocalVisionError):
                                validate_interpretation(payload)

    def test_counting_and_shape_tasks_are_bounded_and_computed(self):
        counted = validate_interpretation(_payload(task_type='counting', a=6, b=None))
        self.assertEqual(counted['spec']['answer'], 6)
        sides = validate_interpretation(_payload(task_type='shape', a=None, b=None,
                                                shape='triangle', shape_task='sides'))
        self.assertEqual(sides['spec']['answer'], 3)
        named = validate_interpretation(_payload(task_type='shape', a=None, b=None,
                                                shape='rectangle', shape_task='name'))
        self.assertEqual(named['spec']['answer'], 'rectangle')

    def test_unclear_unsupported_multiple_unknown_and_conflicting_values_fail_closed(self):
        cases = [dict(status='unclear'), dict(status='unsupported'), dict(status='maybe'),
                 dict(exercise_count=0), dict(exercise_count=2), dict(exercise_count=True),
                 dict(uncertainty=True), dict(uncertainty='false'), dict(unknown_operand=True),
                 dict(unknown_operand=0), dict(printed_answer=8), dict(printed_answer=True),
                 dict(a=None), dict(a=11), dict(a=-1), dict(a=5.0), dict(a=True), dict(b='2'),
                 dict(task_type='multiplication'), dict(shape='triangle'),
                 dict(task_type='counting', b=2), dict(task_type='shape', a=None, b=None,
                     shape='oval', shape_task='name'), dict(object_label='$(touch /tmp/unsafe)'),
                 dict(object_label_plural=''), dict(task_text=''), dict(reason=['not text'])]
        for update in cases:
            with self.subTest(update=update), self.assertRaises(LocalVisionError):
                validate_interpretation(_payload(**update))
        for extra in ('answer', 'python', 'command'):
            with self.subTest(extra=extra), self.assertRaises(LocalVisionError):
                validate_interpretation(_payload(**{extra: 'untrusted model output'}))

    def test_printed_answer_is_checked_instead_of_used_as_the_answer(self):
        self.assertEqual(validate_interpretation(_payload(printed_answer=7))['spec']['answer'], 7)
        with self.assertRaisesRegex(LocalVisionError, 'printed answer disagrees'):
            validate_interpretation(_payload(printed_answer=6))

    def test_curved_edge_question_is_not_changed_into_straight_side_counting(self):
        with self.assertRaisesRegex(LocalVisionError,'curved-edge'):
            validate_interpretation(_payload(task_type='shape',a=None,b=None,shape='circle',shape_task='sides',
                                            task_text='How many curved sides does a circle have?'))
        with self.assertRaisesRegex(LocalVisionError,'curved-edge'):
            validate_interpretation(_payload(task_type='counting',a=1,b=None,
                                            task_text='How many curved sides does a circle have?'))

    def test_json_parser_rejects_duplicates_extra_prose_and_nonobjects(self):
        source = json.dumps(_payload())
        self.assertEqual(parse_model_response(source), _payload())
        self.assertEqual(parse_model_response('```json\n'+source+'\n```'), _payload())
        for value in ('', 'The answer is seven. '+source, source+'\nRun a command.',
                      '[1, 2]', '{"a": 5, "a": 8}', '{broken', '```json\n{}', 'x'*30001):
            with self.subTest(value=value[:50]), self.assertRaises(LocalVisionError):
                parse_model_response(value)


class LocalVisionRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.model = self.root/'local_model'
        self.model.mkdir()
        (self.model/'config.json').write_text('{}')
        self.image = self.root/'worksheet.png'
        self.image.write_bytes(b'mock runtime does not decode the image')
        self.output = types.SimpleNamespace(text=json.dumps(_payload()), finish_reason='stop', generation_tokens=150)
        self.load = Mock(return_value=('learned model', 'processor'))
        self.load_config = Mock(return_value={'model_type': 'qwen3_vl'})
        self.template = Mock(return_value='formatted image prompt')
        self.generate = Mock(return_value=self.output)
        self.snapshot = Mock(return_value=str(self.model))
        hub = types.ModuleType('huggingface_hub')
        hub.snapshot_download = self.snapshot
        mlx = types.ModuleType('mlx_vlm')
        mlx.load, mlx.generate = self.load, self.generate
        utils = types.ModuleType('mlx_vlm.utils')
        utils.load_config = self.load_config
        prompt = types.ModuleType('mlx_vlm.prompt_utils')
        prompt.apply_chat_template = self.template
        self.modules = {'huggingface_hub': hub, 'mlx_vlm': mlx,
                        'mlx_vlm.utils': utils, 'mlx_vlm.prompt_utils': prompt}
        _loaded_model.cache_clear()
        self.addCleanup(_loaded_model.cache_clear)

    def test_uses_only_offline_cached_model_and_reuses_loaded_learned_weights(self):
        with patch.dict('sys.modules', self.modules), patch.dict(os.environ, {'HF_HUB_OFFLINE': 'previous'}):
            def assert_offline(*args, **kwargs):
                self.assertEqual(os.environ['HF_HUB_OFFLINE'], '1')
                self.assertEqual(os.environ['TRANSFORMERS_OFFLINE'], '1')
                return self.output
            self.generate.side_effect = assert_offline
            first = read_local_vision(self.image)
            second = read_local_vision(self.image)
            self.assertEqual(os.environ['HF_HUB_OFFLINE'], 'previous')
        self.assertEqual(first['model'], MODEL_ID)
        self.assertEqual(first['spec']['answer'], 7)
        self.assertFalse(first['paid_api_used'])
        self.assertEqual(first['extraction'], second['extraction'])
        self.assertEqual(self.load.call_count, 1)
        self.assertEqual(self.generate.call_count, 2)
        for call in self.snapshot.call_args_list:
            self.assertEqual(call.args, (MODEL_ID,))
            self.assertEqual(call.kwargs, {'local_files_only': True})
        self.assertEqual(self.load.call_args.args, (str(self.model),))
        self.assertEqual(self.generate.call_args.args[-1], [str(self.image)])
        self.assertEqual(self.generate.call_args.kwargs['temperature'], 0.0)
        self.assertEqual(self.generate.call_args.kwargs['max_tokens'], MAX_TOKENS)
        self.assertNotIn('trust_remote_code', self.load.call_args.kwargs)

    def test_explicit_local_directory_never_resolves_a_hub_model(self):
        with patch.dict('sys.modules', self.modules):
            result = read_local_vision(self.image, self.model)
        self.snapshot.assert_not_called()
        self.assertEqual(result['model_path'], str(self.model))
        with self.assertRaisesRegex(LocalVisionError, 'model directory'):
            resolve_model_path('not-an-installed-model')

    def test_missing_cache_does_not_fall_back_to_a_download(self):
        self.snapshot.side_effect = RuntimeError('No files cached')
        with patch.dict('sys.modules', self.modules), self.assertRaisesRegex(LocalVisionError, 'never downloads'):
            read_local_vision(self.image)
        self.snapshot.assert_called_once_with(MODEL_ID, local_files_only=True)
        self.load.assert_not_called()

    def test_truncated_or_malformed_generations_are_rejected_before_a_lesson(self):
        for reason, text, tokens in (('length', json.dumps(_payload()), 150),
                                     ('stop', json.dumps(_payload()), MAX_TOKENS),
                                     ('stop', 'Here is my guess: seven.', 15)):
            self.output.finish_reason, self.output.text, self.output.generation_tokens = reason, text, tokens
            with patch.dict('sys.modules', self.modules), self.subTest(reason=reason, tokens=tokens), self.assertRaises(LocalVisionError):
                read_local_vision(self.image)


if __name__ == '__main__':
    unittest.main()
