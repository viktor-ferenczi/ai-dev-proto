from pprint import pprint

import interegular
from outlines.fsm.regex import make_deterministic_fsm, create_fsm_index_tokenizer

from transformers import AutoTokenizer

DEEPSEEK_CODER_TOKENIZER = AutoTokenizer.from_pretrained('TheBloke/deepseek-coder-1.3b-base-AWQ')
DEEPSEEK_CODER_TOKENIZER.vocabulary = DEEPSEEK_CODER_TOKENIZER.vocab
DEEPSEEK_CODER_TOKENIZER.special_tokens = DEEPSEEK_CODER_TOKENIZER.special_tokens_map
DEEPSEEK_CODER_TOKENIZER.convert_token_to_string = lambda x: DEEPSEEK_CODER_TOKENIZER.convert_tokens_to_string([x])

regex_string = r'```\n(Program\.cs\n)?```\n'
regex_pattern = interegular.parse_pattern(regex_string)
regex_fsm, _ = make_deterministic_fsm(regex_pattern.to_fsm().reduce())
states_to_token_maps, empty_token_ids = create_fsm_index_tokenizer(regex_fsm, DEEPSEEK_CODER_TOKENIZER)

pprint(states_to_token_maps)
