"""Current news model selection; historical trial pins are deliberately separate."""
import os

DEFAULT_MODEL = 'gpt-6-sol'
SUPPORTED_MODELS = ('gpt-5.4-mini', DEFAULT_MODEL)


def selected_model():
    return os.environ.get('NEWS_OPENAI_MODEL', DEFAULT_MODEL)


def reservation_micro_usd(model, input_bound, output_bound):
    if any(type(n) is not int or n < 0 for n in (input_bound, output_bound)):
        raise ValueError('news_invalid_token_bound')
    if model == 'gpt-6-sol':
        # Worst standard short-context input: 12h cache writes, not a cache discount.
        return input_bound * 5 + output_bound * 10
    if model == 'gpt-5.4-mini':
        return (input_bound * 3 + output_bound * 18 + 3) // 4
    raise ValueError('news_unpriced_model')
