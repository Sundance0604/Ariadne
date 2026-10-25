"""Validate manual audio/video mappings without extrapolating unreviewed gaps."""
import math


def validate_anchors(anchors,master_duration,video_duration):
    if not isinstance(anchors,list) or len(anchors)<2:
        raise ValueError('至少需要两个音画锚点')
    previous=(-1,-1)
    for anchor in anchors:
        m,v=anchor.get('masterTime'),anchor.get('videoTime')
        if any(not isinstance(t,(int,float)) or isinstance(t,bool) or not math.isfinite(t) for t in [m,v]):
            raise ValueError('锚点时间必须是有限数值')
        if not 0<=m<=master_duration or not 0<=v<=video_duration or m<=previous[0] or v<=previous[1]:
            raise ValueError('锚点必须在两条媒体时间轴内严格递增')
        previous=(m,v)
    return anchors
