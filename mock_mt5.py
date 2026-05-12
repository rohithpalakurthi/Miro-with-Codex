from datetime import datetime, timedelta
import pandas as pd
import numpy as np

TIMEFRAME_M1 = 1
TIMEFRAME_M5 = 5
TIMEFRAME_M15 = 15
TIMEFRAME_M30 = 30
TIMEFRAME_H1 = 60
TIMEFRAME_H4 = 240
TIMEFRAME_D1 = 1440

def initialize(*args, **kwargs):
    return True

def login(*args, **kwargs):
    return True

def shutdown(*args, **kwargs):
    pass

def last_error():
    return (1, "Success")

class DictLikeMock:
    def __init__(self, **kwargs):
        self._dict = kwargs
        for k, v in kwargs.items():
            setattr(self, k, v)
    def __getattr__(self, name):
        if name in self._dict:
            return self._dict[name]
        raise AttributeError(name)
    def __iter__(self):
        return iter(self._dict)
    def __getitem__(self, key):
        return self._dict[key]
    def _asdict(self):
        return self._dict
    def keys(self):
        return self._dict.keys()

def account_info():
    return DictLikeMock(
        balance=10000.0,
        equity=10000.0,
        margin=0.0,
        margin_free=10000.0,
        margin_level=0.0,
        profit=0.0,
        leverage=100,
        name="MockAccount"
    )

def positions_get(*args, **kwargs):
    return ()

def copy_rates_from_pos(symbol, timeframe, start_pos, count):
    if count == 0: count = 1
    end_time = datetime.now()
    start_time = end_time - timedelta(days=count)
    df = pd.DataFrame(index=pd.date_range(start=start_time, end=end_time, periods=count))
    df['open'] = 2000.0
    df['high'] = 2005.0
    df['low'] = 1995.0
    df['close'] = 2000.0
    df['tick_volume'] = 100
    df['spread'] = 1
    df['real_volume'] = 100
    df['time'] = (df.index - pd.Timestamp("1970-01-01")) // pd.Timedelta('1s')

    records = np.core.records.fromarrays(
        [df['time'], df['open'], df['high'], df['low'], df['close'], df['tick_volume'], df['spread'], df['real_volume']],
        names='time,open,high,low,close,tick_volume,spread,real_volume'
    )
    return tuple(records)

def copy_rates_range(symbol, timeframe, date_from, date_to):
    df = pd.DataFrame(index=pd.date_range(start=date_from, end=date_to, periods=100))
    df['open'] = 2000.0
    df['high'] = 2005.0
    df['low'] = 1995.0
    df['close'] = 2000.0
    df['tick_volume'] = 100
    df['spread'] = 1
    df['real_volume'] = 100
    df['time'] = (df.index - pd.Timestamp("1970-01-01")) // pd.Timedelta('1s')
    df = df.dropna()

    records = np.core.records.fromarrays(
        [df['time'], df['open'], df['high'], df['low'], df['close'], df['tick_volume'], df['spread'], df['real_volume']],
        names='time,open,high,low,close,tick_volume,spread,real_volume'
    )
    return tuple(records)

def symbol_info_tick(symbol):
    return DictLikeMock(
        ask=2000.0,
        bid=1999.5,
        last=2000.0,
        time=int(datetime.now().timestamp())
    )

def symbol_info(symbol):
    return DictLikeMock(name=symbol, visible=True)

def order_send(*args, **kwargs):
    return DictLikeMock(retcode=10009, order=12345)

def symbol_select(symbol, selected):
    pass
