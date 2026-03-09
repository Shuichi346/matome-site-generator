"""ペルソナ定義とシステムプロンプト生成モジュール

2ちゃんねらー風のペルソナを自動生成し、
各エージェントに個性を持たせる。
"""

import random
import string
from dataclasses import dataclass


@dataclass
class Persona:
    """掲示板住人のペルソナ定義"""
    name: str           # 名無し風の表示名
    display_id: str     # ID表示（例: ID:a3Kx9pB0）
    personality: str    # 性格の概要
    speech_style: str   # 口調の説明
    stance: str         # 議論への立場

# 名前のプール
NAME_POOL = [
    "名無しさん＠お腹いっぱい。",
    "名無しさん＠実況は禁止です",
    "風吹けば名無し",
    "名無しさん＠おーぷん",
    "以下、名無しにかわりましてVIPがお送りします",
    "名無しさん＠涙目です。",
    "名無しさん＠恐縮です",
    "名無しさん＠お金いっぱい。",
    "名無しさん＠編集中",
    "名無しさん＠そうだ選挙に行こう",
]

# 口調のプール
SPEECH_STYLE_POOL = [
    "丁寧語で論理的に話す。根拠を示しながら意見を述べる",
    "草を多用するノリの軽い話し方。「ワロタ」「草」を連発する",
    "煽り気味で断定的。「〜だろ常識的に考えて」が口癖",
    "やたら長文で語る古参風。「昔はな…」と懐古する",
    "短文でツッコミを入れるスタイル。一言でバッサリ切る",
    "方言混じりで親しみやすい口調。関西弁っぽい",
    "やる気のない脱力系。「〜しらんけど」が口癖",
    "知識マウントを取りたがる。専門用語を多用する",
    "すぐ話を脱線させるムードメーカー。面白い例えを使う",
    "句読点を使わずテンション高め。顔文字を多用する",
]

# 性格のプール
PERSONALITY_POOL = [
    "冷静で分析的。データや事実を重視する",
    "熱血で情熱的。好きなものへの愛が深い",
    "皮肉屋で辛口。でも的を射た指摘をする",
    "お人好しで共感力が高い。みんなの意見に理解を示す",
    "天邪鬼で逆張り好き。多数派と逆の意見を言いがち",
    "オタク気質で細部にこだわる。マニアックな知識が豊富",
    "社交的でまとめ役。議論の流れを整理しようとする",
    "飽きっぽくて気まぐれ。話題をころころ変える",
    "慎重派で石橋を叩いて渡るタイプ。リスクを気にする",
    "楽観的でポジティブ。何でも良い方に解釈する",
]

# 立場のプール（トーンに応じて調整される）
STANCE_POOL_BALANCED = ["賛成寄り", "反対寄り", "中立", "やや賛成", "やや反対"]
STANCE_POOL_SUPPORTIVE = ["賛成寄り", "強く賛成", "やや賛成", "中立", "賛成寄り"]
STANCE_POOL_CRITICAL = ["反対寄り", "強く反対", "やや反対", "中立", "反対寄り"]


def _generate_random_id(length: int = 8) -> str:
    """擬似ランダムなID文字列を生成する"""
    chars = string.ascii_letters + string.digits
    return "".join(random.choice(chars) for _ in range(length))


def _select_stance_pool(tones: list[str]) -> list[str]:
    """選択されたトーンに応じて立場プールを決定する"""
    if "賛成多め" in tones:
        return STANCE_POOL_SUPPORTIVE
    if "批判的" in tones:
        return STANCE_POOL_CRITICAL
    if "白熱" in tones or "煽り" in tones or "にわか vs 古参" in tones:
        # 対立する立場を多くする
        return ["賛成寄り", "強く賛成", "反対寄り", "強く反対", "中立"]
    return STANCE_POOL_BALANCED


def generate_personas(count: int, tones: list[str]) -> list[Persona]:
    """指定人数分のペルソナを生成する

    Args:
        count: 生成するペルソナの数
        tones: ユーザーが選んだ議論トーンのリスト

    Returns:
        ペルソナのリスト
    """
    stance_pool = _select_stance_pool(tones)
    personas: list[Persona] = []

    # 名前・口調・性格をシャッフルして割り当て
    names = random.sample(NAME_POOL, min(count, len(NAME_POOL)))
    if count > len(NAME_POOL):
        names += random.choices(NAME_POOL, k=count - len(NAME_POOL))

    styles = random.sample(SPEECH_STYLE_POOL, min(count, len(SPEECH_STYLE_POOL)))
    if count > len(SPEECH_STYLE_POOL):
        styles += random.choices(SPEECH_STYLE_POOL, k=count - len(SPEECH_STYLE_POOL))

    personalities = random.sample(
        PERSONALITY_POOL, min(count, len(PERSONALITY_POOL))
    )
    if count > len(PERSONALITY_POOL):
        personalities += random.choices(
            PERSONALITY_POOL, k=count - len(PERSONALITY_POOL)
        )

    # トーンに応じた口調の強制追加
    if "煽り" in tones and count > 0:
        styles[0] = "煽り気味で断定的。「〜だろ常識的に考えて」が口癖"
    if "ネタ・ボケ" in tones and count > 1:
        styles[-1] = "すぐ話を脱線させるムードメーカー。面白い例えを使う"
    if "懐古厨" in tones and count > 2:
        styles[1] = "やたら長文で語る古参風。「昔はな…」と懐古する"

    for i in range(count):
        persona = Persona(
            name=names[i],
            display_id=_generate_random_id(),
            personality=personalities[i],
            speech_style=styles[i],
            stance=random.choice(stance_pool),
        )
        personas.append(persona)

    return personas


def build_system_prompt(
    persona: Persona,
    theme: str,
    context: str,
    tones: list[str],
) -> str:
    """ペルソナ情報とテーマからシステムプロンプトを生成する

    Args:
        persona: ペルソナ定義
        theme: 議論のテーマ
        context: 議論の補足情報
        tones: 議論トーンのリスト

    Returns:
        システムプロンプト文字列
    """
    tone_str = "、".join(tones) if tones else "通常"

    prompt = f"""あなたは日本の匿名掲示板（2ちゃんねる/5ちゃんねる）の住人です。
以下の設定に従い、掲示板風の投稿を1レスだけ書いてください。

【あなたの設定】
- 表示名: {persona.name}
- ID: {persona.display_id}
- 性格: {persona.personality}
- 口調: {persona.speech_style}
- 立場: {persona.stance}

【議論のテーマ】
{theme}

【議論の補足情報】
{context if context else "特になし"}

【議論のトーン】
{tone_str}

【ルール】
- 1回の投稿で1レスのみ書く（レス番号や名前行は書かない。本文のみ）
- 他の人のレスに反応しても良い（アンカー >> を使う）
- 2ch/5ch風の自然な会話をする
- 顔文字やAA（アスキーアート）を適度に使って良い
- 「ワロタ」「草」「〜だろ」「〜じゃね？」などの掲示板特有の表現を使う
- レスの長さは150文字程度にする（長文キャラの場合はもう少し長くても良い）
- 他の住人と議論をする。前のレスの流れに沿う
- 自分のキャラクター設定を一貫して守る
- レス内で自分の名前やIDを名乗らない

【参考：2chレスの例】
「まあそれな。でも俺は逆だと思うわ」
「>>3 それはお前の感想やろ草」
「いやマジでこれ。ソースあるなら出してみろよ」
「ワロタ。確かにそうかもしれんｗｗｗ」
"""
    return prompt
