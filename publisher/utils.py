import re


def updateDictDelta(obj, delta):
    for key, value in delta.items():
        if key not in obj:
            obj[key] = value
        elif type(value) == dict and type(obj[key]) == dict:
            obj[key] = updateDictDelta(obj[key], value)
        elif (
            type(value) == dict
            and type(obj[key]) == list
            and all([k.isnumeric() for k in value.keys()])
        ):
            tempDict = dict([(str(idx), value) for idx, value in enumerate(obj[key])])
            tempDict = updateDictDelta(tempDict, value)
            obj[key] = [value for _, value in tempDict.items()]
        else:
            obj[key] = value
    return obj


def timeStr2msec(timeStr: str):
    return (
        sum(
            [
                val * scaler
                for val, scaler in zip(
                    reversed([float(i) for i in re.split(":", timeStr)]), [1, 60]
                )
            ]
        )
        * 1000
    )


def msec2timeStr(msec: int, signed: bool = False):
    val = int(abs(msec))
    if signed:
        timeStr = "+" if msec >= 0 else "-"
    else:
        timeStr = "" if msec >= 0 else "-"
    if val >= 60000:
        timeStr += str(val // 60000) + ":"
        val %= 60000
    timeStr += str(val // 1000)
    timeStr += "." + str(val % 1000).zfill(3)
    return timeStr
