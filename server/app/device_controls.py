"""Small explicit device commands; applied receipts precede spoken success."""
import asyncio,json,re,uuid

def parse(text,settings):
    text=re.sub(r'[\u0591-\u05c7]','',text.lower()).replace('ווליום','עוצמה').replace('ווליאום','עוצמה')
    # Descriptions, questions about capability, quoted and negative commands are not actions.
    if re.search(r'\b(אל|לא|אמר|אמרה|אמרתי|שאלתי|למה|מדוע)\b',text) or any(c in text for c in '"״'):return None
    if re.search(r"בסלון|בחדר|בטלוויזיה|במחשב|בטלפון|באייפון|במטבח|מוזיקה|מוסיקה",text):return None
    fields=[]
    if re.search(r'בהירות|בהיר|תעמעם|עמעם|תבהיר',text):fields.append('brightness')
    if re.search(r'עוצמה|עוצמת|רמקול|קול',text):fields.append('volume')
    if len(fields)!=1:return None
    key=fields[0]
    down=bool(re.search(r'הנמך|תנמיך|להנמיך|הורד|תוריד|להוריד|תעמעם|עמעם|חלש יותר|פחות בהיר',text))
    up=bool(re.search(r'הגבר|תגביר|להגביר|העלה|תעלה|להעלות|תבהיר|חזק יותר|יותר בהיר',text))
    absolute=bool(re.search(r'הגדר|תגדיר|להגדיר|כוון|תכוון|קבע|תקבע',text))
    if not (down or up or absolute) or (down and up):return None
    if re.search(r'(?<!\w)-\d',text):return None
    nums=re.findall(r'\d+(?:\.\d+)?',text)
    percent=None
    for word,n in [('מאה',100),('חמישים',50),('שלושים',30),('עשרים',20),('עשר',10),('אפס',0)]:
        if re.search(r'\b[לב]?[־\- ]?'+word+r'\b',text):percent=n;break
    if nums:
        if len(nums)!=1:return None
        percent=float(nums[0])
    current=settings.get(key,170 if key=='brightness' else 80)
    current=current*100/255 if key=='brightness' else current
    if percent is not None:
        if not 0<=percent<=100:return None
        # "ב־10" is a delta, "ל־30" / "30 אחוז" is an absolute level.
        delta=bool(re.search(r'ב[־\- ]?(?:\d|עשר|עשרים)',text))
        level=current+(-percent if down else percent) if delta and not absolute else percent
    elif absolute:return None
    else:level=current+(-10 if down else 10)
    value=max(20,min(255,round(level*255/100))) if key=='brightness' else max(0,min(100,round(level)))
    return {key:value}

async def apply(text,hub,admin,emit):
    values=parse(text,admin.settings())
    if values is None:return None
    if not any(c.kind=='board' for c in hub.conns):return 'המכשיר אינו מחובר, לכן ההגדרה לא שונתה.'
    cid=uuid.uuid4().hex;receipt=asyncio.get_running_loop().create_future();hub.receipts[cid]=receipt
    try:
        await hub.emit({'type':'config','command_id':cid,**values},only_kind='board')
        result=await asyncio.wait_for(receipt,5)
        if result.get('status')!='applied':return 'המכשיר לא אישר את השינוי. אפשר לנסות שוב.'
    except TimeoutError:return 'לא התקבל אישור מהמכשיר לשינוי. אפשר לנסות שוב.'
    finally:hub.receipts.pop(cid,None)
    saved=admin.settings();saved.update(values)
    admin.SETTINGS_FILE.write_text(json.dumps(saved,ensure_ascii=False));admin.apply_settings()
    await emit({'type':'settings.updated','settings':admin.current_settings()})
    key=next(iter(values));value=values[key]
    if key=='brightness':return f'הבהירות הוגדרה ל־{round(result.get("effective_brightness",value)*100/255)} אחוזים.'
    return f'עוצמת הקול הוגדרה ל־{value} אחוזים.'
