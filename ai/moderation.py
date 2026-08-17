from __future__ import annotations
import re
LINK_RE=re.compile(r"(?:https?://|www\.|t\.me/|telegram\.me/|tg://|telegram\.dog/|(?:[a-z0-9-]+\.)+(?:com|ir|org|net|io|me|cc)(?:/|\b))",re.IGNORECASE)
MENTION_RE=re.compile(r"(?<!\w)@[A-Za-z0-9_]{2,32}(?!\w)")
HASHTAG_RE=re.compile(r"(?<!\w)#[A-Za-z0-9_\u0600-\u06FF]+",re.UNICODE)
PHONE_RE=re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)")
PROFANITY_TERMS={"کسکش","کونی","جنده","حرومزاده","fuck","motherfucker","bitch"}
DRUG_TERMS={"کوکائین","کراک","شیشه","هروئین","تریاک","ماریجوانا","گل","مواد مخدر","cocaine","heroin","meth","marijuana","weed"}
NSFW_TERMS={"porn","porno","pornography","سکس","پورن"}
def normalize(text:str)->str:
    text=text.casefold().replace("ي","ی").replace("ى","ی").replace("ك","ک").replace("ة","ه")
    return re.sub(r"[\u200c\u200d\u200e\u200f\ufeff\s\-_\.]+","",text)
class ModerationEngine:
    def contains_link(self,text:str)->bool:return bool(LINK_RE.search(text or ""))
    def contains_mention(self,text:str)->bool:return bool(MENTION_RE.search(text or ""))
    def contains_hashtag(self,text:str)->bool:return bool(HASHTAG_RE.search(text or ""))
    def contains_phone(self,text:str)->bool:return bool(PHONE_RE.search(text or ""))
    @staticmethod
    def _contains_term(text:str,terms:set[str])->bool:
        normalized=normalize(text or "");return any(normalize(term) in normalized for term in terms)
    def contains_profanity(self,text:str)->bool:return self._contains_term(text,PROFANITY_TERMS)
    def contains_drug_content(self,text:str)->bool:return self._contains_term(text,DRUG_TERMS)
    def contains_nsfw_content(self,text:str)->bool:return self._contains_term(text,NSFW_TERMS)
    def looks_like_flood(self,recent_message_count:int,threshold:int=8)->bool:return recent_message_count>=threshold
    def classify(self,text:str)->str:
        if self.contains_link(text):return "link"
        if self.contains_drug_content(text):return "drug"
        if self.contains_nsfw_content(text):return "nsfw"
        if self.contains_profanity(text):return "profanity"
        if self.contains_mention(text):return "mention"
        if self.contains_hashtag(text):return "hashtag"
        return "normal"
moderation_engine=ModerationEngine()
