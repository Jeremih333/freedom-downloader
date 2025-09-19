from aiogram.fsm.state import StatesGroup, State

class DownloadStates(StatesGroup):
    waiting_for_link = State()
    waiting_for_format = State()
    waiting_for_confirmation = State()
