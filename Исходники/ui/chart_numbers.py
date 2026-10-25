"""Показывает числа карточки точки без экспонент и длинных дробных хвостов."""

from decimal import Decimal,InvalidOperation,ROUND_HALF_UP,localcontext


def human_number(value):
    try:number=Decimal(str(value))
    except (InvalidOperation,ValueError):return '—'
    if not number.is_finite():return '—'
    if number and abs(number)<Decimal('0.000000000001'):
        return '< 0,000000000001' if number>0 else '> -0,000000000001'
    places=2 if abs(number)>=1 or not number else min(12,2-number.adjusted())
    with localcontext() as context:
        context.prec=max(28,len(number.as_tuple().digits)+abs(number.adjusted())+places+4)
        rounded=number.quantize(Decimal(1).scaleb(-places),rounding=ROUND_HALF_UP)
        result=format(rounded if rounded else Decimal(0),',f')
    if '.' in result:result=result.rstrip('0').rstrip('.')
    return result.replace(',',' ').replace('.',',')
