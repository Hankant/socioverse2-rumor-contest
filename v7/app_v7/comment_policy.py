"""Latest public comment window and voluntary, personality-aware participation."""
import copy
import hashlib
import json

LATEST_FEED_POLICY = 'network_rumor_latest_comments_v1'
PARTICIPATION_POLICY = 'mbti_voluntary_comment_v1'
MEMORY_POLICY = 'personal_actions_no_comment_transcripts_v1'


def comment_limit(physical):
    """V7 exposes at most thirty previous-tick comments per visible root."""
    limit = physical.get('comment_window_limit', 30)
    if type(limit) is not int or limit != 30:
        raise ValueError('latest comment policy requires comment_window_limit=30')
    return limit


def recent_comments(comments, limit, seed):
    """Tick is the simulation's time resolution; seeded ties avoid ID bias."""
    def order(c):
        tie=hashlib.sha256(f"{seed}|{c['published_tick']}|{c['comment_id']}".encode()).hexdigest()
        return -c['published_tick'],tie,c['comment_id']
    return sorted(copy.deepcopy(comments),key=order)[:limit]


def personal_memory_posts(feed):
    """Archive decisions separately; do not replay old public threads as memory."""
    result=copy.deepcopy(feed)
    for post in result:
        comments=post['comments']
        post['observed_comment_count']=len(comments)
        post['observed_comment_sha256']=hashlib.sha256(json.dumps(
            comments,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        post['comments']=[]
        post['comment_memory_policy']=MEMORY_POLICY
    return result


def policy_instructions(physical):
    if physical.get('comment_participation_policy')!=PARTICIPATION_POLICY:
        return ''
    from memory_policy import memory_description
    limit = comment_limit(physical)
    return (
        '\n【自愿评论：MBTI与个人情境共同决定】'
        '先决定本轮是否愿意公开评论，再决定写什么。只阅读、形成评分而不评论是完整且正常的参与，'
        '不因被要求输出JSON或condition_application就发表评论；无补充、无想表达的观点时可保持沉默，'
        '不要每轮重复上一轮意见或为凑参与而评论。'
        '结合本人MBTI四维偏好及强度：E/I影响是否愿意进入公开互动或先独自消化，'
        'S/N影响是否有具体细节或联系值得表达，T/F影响想澄清逻辑还是表达处境关切，'
        'J/P影响是否希望明确表态还是继续观察。偏好不等于固定行为，I也可评论、E也可沉默。'
        '再结合年龄、地区、职业、社区经历、来源/政府信任、核验偏好、分享倾向、重复敏感度、'
        '本人历史及当前帖子和评论，判断是否有个人表达动机。相信/不相信都不自动要求评论，'
        '评论和转发分别决定，不设全体或人格类型的固定评论比例。'
        '在mbti_preferences的affects中必须包含comment；其note简述本人偏好如何影响本轮评论或沉默。'
        '不评论则comment.enabled=false、target_content_id=null、text=""。'
        '\n【当前评论窗口与个人记忆】'
        f'每个实际可见主帖只展示截至上一轮已发布的最新{limit}条评论；不足{limit}条则展示全部，'
        '正文原文保留，未展示的旧评论不可假装已读。模拟只有轮次时间，同轮评论用固定种子排序打破并列，'
        '该排序不是现实发表时间，也不是热度或赞同度。SOURCE与GOVERNMENT独立评论区各自计数。'
        +memory_description(physical)+'；保留自己的判断、评分、评论/转发和实际接触记录，'
        '不重新提供当时其他人的评论全文；历史中的评论数量/哈希只是接触记录，不是可阅读的评论内容。'
    )
