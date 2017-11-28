#!/usr/bin/env python3
import time         # для таймеров
import threading    # для тредов
import gi           # для gui
import serial       # для uart
import simpleaudio as sa  # для аудио
import cairo        # для визуальных эффектов
import cobs         # для декодирования сообщений из uart
import os           # чтобы иметь возможность слать команды os
try:
    import RPi.GPIO as GPIO  # для работы с GPIO
    gpio = True

except:
    print("Error importing RPi.GPIO!")
    gpio = False
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Pango, GLib, Gdk

###################################################################################
'''
Принцип работы таймера:
Используется кнопка Select для выбора режима работы таймера;
Кнопка Start - запускай таймер;
Кнопка Pause - ставит/снимает таймер с паузы;
Кнопка Reset - сбрасывает таймер в зависимости от режима;
Кнопка Выкл - выключает компьютер полностью;
Поворотная ручка используется для задания времени таймера.
Таймер может работать в трех режимах: искатель, экстремал, просто обратный отсчет.

В режиме ИСКАТЕЛЬ, при нажатии на кнопку Start - начинается обратный отсчет 3 минуты на подготовку,
потом сразу начинается попытка - 10 минут.
Повторное нажатие на кнопку Start до окончания времени на подготовку сразу запускает попытку на 10 минут.

В режиме ЭКСТРЕМАЛ и ЭКСТРЕМАЛ Pro, при нажатии на кнопку Start - начинается обраатный отсчет 7 минут на подготовку,
потом сразу начинается попытка - 10 минут.
Повторное нажатие на кнопку Start до окончания времени на подготовку сразу запускает попытку на 10 минут.

В режиме ОБРАТНОГО ОТСЧЕТА время задается при помощи поворотной ручки с шагом в минуту, после чего при нажати на кнопку
Start начинается обратный отсчет до нуля. Повторное нажатие на кнопку Start досрочно останавливает таймер.

При изменении режима работы таймера - отсчет останавливается в любом случае.
'''
####################################################################################
# режимы таймера (нужны только чтобы писать корректный текст)
pause = 0           # перерыв
finder = 1          # искатель
extremal = 2        # экстремал
extremalPro = 3     # экстремал про
# режим по умолчанию
mode = finder

textPause = "Перерыв/Тренировка/Пауза"
textFinder = "Искатель 2.0"
# textFinderReady = "Искатель. Подготовка"
textExtremal = "Экстремал 1.0"
# textExtremalReady = "Экстремал. Подготовка"
textExtremalPro = "Экстремал Pro 1.0"
# textExtremalProReady = "Экстремал Pro. Подготовка"
textPreparing = "Подготовка"
textAttemptEnd = "Попытка закончена"


pattern = '{0:02d}:{1:02d}'     # формат вывода строки

eventShortBeep = threading.Event()  # события, которыми будем вызывать проигрывание аудио
eventLongBeep = threading.Event()
eventHighBeep = threading.Event()
eventLowBeep = threading.Event()
eventAirHorn = threading.Event()


class MainWindow(Gtk.Window):   # класс основного окна с тремя таймерами
    global mode, pause, finder, extremal

    def __init__(self):
        super(MainWindow, self).__init__()  # переопределяем init
        
        self.set_title("Timer")     # заголовок окна
        # self.set_size_request(800,600)
        self.fullscreen()   # растягиваем на весь экран
        self.connect("destroy", CloseProgram)    # связываем закрытие окна с функцией заверщеия программы
        self.drawArea = Gtk.DrawingArea()   # создаем drawing area на которой будем рисовать приложение
        self.drawArea.connect("draw", self.expose)   # связываем событие с функцией перерисовки содержимого
        self.add(self.drawArea)     # добавляем drawing area в окно приложения
        self.isRunning = True   # флаг что программа работает
        self.alpha = 0    # начальное значение прозрачности (альфа канал, 0 - полностью прозрачен)
        GLib.timeout_add(100, self.on_timer)    # таймер по которому каждые 100 мс будем перерисовывать содержимое
        self.prevTime = 5   # значение с которого будем рисовать красивый обратный отсчет
        self.show_all()     # отображаем окно
        cursor = Gdk.Cursor.new(Gdk.CursorType.BLANK_CURSOR)    # скрываем курсор
        self.get_window().set_cursor(cursor)
        self.currentTime = [0, 0]

        ####служебные переменные
        self.width = 0
        self.height = 0
        self.lineHeight = self.height / 5  # задаем высоту строки = 1/5  высоты экрана
        self.maxSize = self.lineHeight * 3
        self.stepSize = self.maxSize / 10  # шаг с которым будем увеличивать размер шрифта
        self.size = self.maxSize / 10

    def on_timer(self):
        if not self.isRunning:
            return False
        
        self.drawArea.queue_draw()    # по таймеру дергаем событие на перерисовку
        return True

    def expose(self, widget, cr):
        self.width = self.get_size()[0]     # получаем значения ширины и высоты
        self.height = self.get_size()[1]
        cr.set_source_rgb(0, 0, 0)    # фон красим в черный
        cr.paint()  # заливаем фон
        self.currentTime = mainTimer.currentTime
        # cr.select_font_face("DejaVu Sans",cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        # выставляем параметры шрифта
        cr.select_font_face("Digital Dismay", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        if mainTimer.finalCountdown is True and not mode == pause:   # если тикают последние 5 секунд главного таймера
            self.size += self.stepSize   # постепенно увеличиваем размер
            if self.currentTime[1] == self.prevTime - 1:  # если значение секунды сменилось
                self.prevTime = self.currentTime[1]    # фиксируем новое значение времени
                self.size = self.height/50  # возвращаем значения размера шрифта
            if self.size >= self.maxSize: self.size = self.maxSize  # ограничиваем максимальный размер шрифта
            cr.set_font_size(self.size)   # задаем размер текста
            # смотрим какую ширину/высоту будет занимать указанный текст
            (x, y, textWidth, textHeight, dx, dy) = cr.text_extents("0")
            # перемещаем курсор туда где будем рисовать (середина экрана)
            cr.move_to(self.width/2 - textWidth/2, self.height/2+textHeight/2)
            cr.set_source_rgb(1, 1, 1)    # задаем цвет текста

            # если дотикал до конца таймер попытки - выводим соответствующий текст
            if(self.currentTime[0] == 0 and self.currentTime[1] == 0 and
                       mainTimer.GetTimerListLen() == 1 and self.size == self.maxSize):
                time.sleep(0.5)     # ждем чуть чуть чтобы ноль явно повисел
                cr.set_font_size(self.lineHeight)  # задаем размер текста
                cr.select_font_face("GOST type A", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
                (x, y, textWidth, textHeight, dx, dy) = cr.text_extents(textAttemptEnd)
                cr.move_to(self.width / 2 - textWidth / 2, self.height / 2 + textHeight / 2)    # рисуем посередине
                # cr.move_to(self.width / 2 - textWidth / 2, self.height / 5)
                cr.set_source_rgb(1, 1, 1)
                cr.show_text(textAttemptEnd)  # выводим текст
            else:
                cr.show_text(str(self.currentTime[1]))  # выводим текст

        else:   # если не идет обратный отсчет последних 5 секунд - рисуем все три таймера
            self.lineHeight = self.height / 5  # задаем высоту строки = 1/5  высоты экрана
            self.size = self.lineHeight
            self.maxSize = self.lineHeight*3
            self.stepSize = self.maxSize/10     # шаг с которым будем увеличивать размер шрифта
            cr.set_source_rgb(1, 1, 1)    # цвет текста - белый
            # выставляем параметры шрифта
            cr.select_font_face("GOST type A", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            if mode == finder:  # если режим ИСКАТЕЛЬ
                if mainTimer.GetTimerListLen() > 1:
                    cr.set_font_size(self.lineHeight/3)   # шрифт доп надписи = 1/3 строки
                    (x, y, textWidth, textHeight, dx, dy) = cr.text_extents(textPreparing)
                    cr.move_to(self.width / 2 - textWidth / 2, self.lineHeight)   # рисуем чуть ниже первой строки
                    cr.show_text(textPreparing)
                cr.set_font_size(self.lineHeight/2)   # шрифт основной надписи = 1/2 строки
                (x, y, textWidth, textHeight, dx, dy) = cr.text_extents(textFinder)
                cr.move_to(self.width/2-textWidth/2, self.lineHeight/2)  # рисуем первой строкой
                cr.show_text(textFinder)

            elif mode == extremal:    # если режим ЭКСТРЕМАЛ
                if mainTimer.GetTimerListLen() > 1:
                    cr.set_font_size(self.lineHeight/3)
                    (x, y, textWidth, textHeight, dx, dy) = cr.text_extents(textPreparing)
                    cr.move_to(self.width / 2 - textWidth / 2, self.lineHeight)
                    cr.show_text(textPreparing)
                cr.set_font_size(self.lineHeight/2)
                (x, y, textWidth, textHeight, dx, dy) = cr.text_extents(textExtremal)
                cr.move_to(self.width/2-textWidth/2, self.lineHeight/2)
                cr.show_text(textExtremal)

            elif mode == extremalPro:  # если режим ЭКСТРЕМАЛ Про
                if mainTimer.GetTimerListLen() > 1:
                    cr.set_font_size(self.lineHeight/3)
                    (x, y, textWidth, textHeight, dx, dy) = cr.text_extents(textPreparing)
                    cr.move_to(self.width / 2 - textWidth / 2, self.lineHeight)
                    cr.show_text(textPreparing)
                cr.set_font_size(self.lineHeight/2)
                (x, y, textWidth, textHeight, dx, dy) = cr.text_extents(textExtremalPro)
                cr.move_to(self.width / 2 - textWidth / 2, self.lineHeight/2)
                cr.show_text(textExtremalPro)

            elif mode == pause:    # если Таймер
                cr.set_font_size(self.lineHeight/2)
                # смотрим какую ширину/высоту будет занимать указанный текст
                (x, y, textWidth, textHeight, dx, dy) = cr.text_extents(textPause)
                cr.move_to(self.width / 2 - textWidth / 2, self.lineHeight/2)
                cr.show_text(textPause)
            # выставляем параметры шрифта
            cr.select_font_face("Digital Dismay", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)

            # cr.set_font_size(self.size)   # шрифт доп таймеров = 1 строка
            # cr.set_source_rgb(1,0,0)    # цвет текста - красный
            # cr.move_to(self.width/4 - textWidth/2, self.height/3)   # перемещаем курсор туда где будем рисовать
            # cr.show_text(redTimer.timeString)  # задаем текст
            #
            # cr.move_to(self.width*3/4 - textWidth/2, self.height/3) # аналогично предыдущему
            # cr.set_source_rgb(0,1,0)    # цвет текста - зеленый
            # cr.show_text(greenTimer.timeString)

            cr.set_font_size(self.lineHeight*3)   # шрифт таймера = 2 строки
            # смотрим какую ширину/высоту будет занимать указанный текст
            (x, y, textWidth, textHeight, dx, dy) = cr.text_extents("00:00")
            cr.move_to(self.width/2 - textWidth/2, self.lineHeight*3.5)
            cr.set_source_rgb(1, 1, 1)    # цвет текста - белый
            cr.show_text(mainTimer.GetTimer())
            self.size = self.maxSize/10

        # self.infoSize = self.height/60  #вывод сервисной информации от пультов, высота строки совсем маленькая
        # cr.set_font_size(self.infoSize)
        # (x,y,textWidth,textHeight,dx,dy) = cr.text_extents("P1: None;")
        # выставляем параметры шрифта
        # cr.select_font_face("DejaVu Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        # cr.set_source_rgb(1,1,1)
        # for i in range(3):  #в цикле выводим статичную часть надписи
        #     cr.move_to(self.width/100+textWidth*1.5*i, self.height*59/60)
        #     cr.show_text("P"+str(i+1)+": ")
        # for i in range(3):  #в цикле же выводим информацию от пультов
        #     cr.move_to(self.width/100+textWidth*1.5*i+textWidth*6/9,self.height*59/60)
        #     if(pult.status[i] == 'None'):   # разным цветом,в зависимости от информации
        #         cr.set_source_rgb(1,0,0)    # красным, если пульта нет, или заряд слишком маленький
        #     elif (pult.status[i] >= 5):
        #         cr.set_source_rgb(0,1,0)    # зеленым, если все хорошо
        #     elif (pult.status[i] < 3):
        #         cr.set_source_rgb(1,0,0)
        #     else:
        #         cr.set_source_rgb(1,1,0)    # желтым если начало садиится
        #     cr.show_text(str(pult.status[i]))

###################################################
'''
Класс для работы таймера. Параметрами являются список таймеров, который включает в себя:
минуты, секунды для нескольких таймеров подряд, и тип таймера - главный, крсный или зеленый.
При работе таймера флаг isRunning позволяет треду работать, флаг isPaused - ставит текущий таймер на паузу.
Если в списке таймеров больше одного элемента - они отсчитываются по очереди,
если он только один - таймер останавливается.
после того как дотикает до конца.
'''
###################################################


class TimerClass(threading.Thread):
    global eventHighBeep, eventAirHorn, eventLowBeep, eventLongBeep, eventShortBeep

    def __init__(self, timerList, timer):
        self.timerList = timerList  # список таймеров
        self.currentTime = [self.timerList[0][0], self.timerList[0][1]]     # записываем время: мин, сек
        self.timeString = pattern.format(self.currentTime[0], self.currentTime[1])  # записываем время в паттерн
        self.timer = timer  # тип таймера
        self.isRunning = False  # флаг, чтобы тред работал
        self.isPaused = True    # флаг, чтобы ставить таймер на паузу
        self.finalCountdown = False     # флаг, что идет отсчет последних 5 секунд
        threading.Thread.__init__(self)

    def Update(self):   # функция обновления таймера
        while self.isRunning:      # пока тред запущен
            if not self.isPaused:  # если таймер не на паузе

                self.currentTime[1] -= 1    # вычитаем одну секунду
                if self.currentTime[1] < 0:     # если секунды кончились
                    if self.currentTime[0] > 0:     # а минуты еще остались
                        self.currentTime[1] = 59    # переписываем секунды
                        self.currentTime[0] -= 1    # вычитаем минуту
                    else:
                        self.currentTime[1] = 0
                    if self.currentTime[0] < 0:
                        self.currentTime[0] = 0

                if self.currentTime[0] == 0 and self.currentTime[1] == 0:   # если дотикали до нуля
                    if self.timer == 'main':    # если остановился главный таймер
                        eventAirHorn.set()  # пищим одним тоном
                    else:   # если любой другой таймер
                        eventHighBeep.set()     # пищим другим тоном

                    if len(self.timerList) > 1:     # если еще остались таймеры, которые нужно дотикать
                        self.timerList.pop(0)       # убираем из списка тот, который кончился
                        self.finalCountdown = False
                        # записываем время нового таймера: мин, сек
                        self.currentTime = [self.timerList[0][0], self.timerList[0][1]]
                        mainWindow.prevTime = 6
                    else:
                        self.isPaused = True    # если это был последний таймер - останавливаем отсчет

                elif self.currentTime[0] == 0 and self.currentTime[1] <= 5:  # если осталось тикать 5 секунд
                    self.finalCountdown = True  # поднимаем флаг, чтобы окно перерисовывалось по другому
                    if self.timer == 'main':   # если отсчет у главного таймера
                        eventLowBeep.set()      # пищим одним тоном
                    else:                       # если у других таймеров
                        eventShortBeep.set()    # другим тоном

                # записываем время в паттерн
                # self.timeString = pattern.format(self.currentTime[0], self.currentTime[1])
                time.sleep(1)   # останавливаем тред на секунду

    def run(self):  # функция для запуска треда
        self.isRunning = True
        eventAirHorn.set()
        self.Update()

    def SetTimerList(self,timerList):   # функция задания нового списка таймеров
        self.isPaused = True    # на всякий случай ставим на паузу
        self.timerList = timerList
        self.currentTime = [self.timerList[0][0], self.timerList[0][1]]
        self.finalCountdown = False
        mainWindow.prevTime = 6

    def Pause(self):    # поставить отсчет на паузу
        self.isPaused = True

    def Resume(self):   # снять отсчет с паузы
        self.isPaused = False

    def GetIsPaused(self):  # получить состояние флага паузы
        return self.isPaused

    def Force(self):    # завершить отсчет текущего таймера, чтобы перейти к следующему
        if not (self.currentTime[0] == 0 and self.currentTime[1] == 0):
            self.isPaused = True
            self.currentTime[0] = 0
            self.currentTime[1] = 1
            self.finalCountdown = True
            self.isPaused = False

    def Exit(self):     # завершить тред
        self.isRunning = False

    def GetCurrentMin(self):    # возвращает число минут которые осталось дотикать
        return self.currentTime[0]

    def GetTimerListLen(self):  # возвращает число таймеров, которые осталось дотикать
        return len(self.timerList)

    def GetTimer(self):
        self.timeString = pattern.format(self.currentTime[0], self.currentTime[1])  # записываем время в паттерн
        return self.timeString

######
'''
Класс для воспроизведения звуковых сигналов. Работает в отдельном потоке. По сути являет собой бесконечный цикл -
обработчик событий. События глобальные, выставляются классом таймера. Когда срабатывает событие - проигрывается
соответствующий звук и событие сбрасывается.
'''
######


class PlayMusic(threading.Thread):  # класс для воспроизведения мелодий
    def __init__(self):
        dirpath = os.getcwd()   # получаем расположение текущей папки
        print("current directory is:", dirpath)
        foldername = os.path.basename(dirpath)  # получаем имя текущей папки
        print("current folder is:", foldername)
        # указываем пути к мелодиям, которые будем проигрывать
        if foldername == "CupTimer":
            print("FilePath: sounds/*.wav")
            self.short_beep = sa.WaveObject.from_wave_file("sounds/short_beep.wav")
            self.long_beep = sa.WaveObject.from_wave_file("sounds/long_beep.wav")
            self.low_beep = sa.WaveObject.from_wave_file("sounds/low_beep.wav")
            self.high_beep = sa.WaveObject.from_wave_file("sounds/high_beep.wav")
            self.horn = sa.WaveObject.from_wave_file("sounds/airhorn.wav")
        else:
            print("FilePath:"+dirpath+"/CupTimer/sounds/*.wav")
            self.short_beep = sa.WaveObject.from_wave_file(dirpath+"/CupTimer/sounds/short_beep.wav")
            self.long_beep = sa.WaveObject.from_wave_file(dirpath+"/CupTimer/sounds/long_beep.wav")
            self.low_beep = sa.WaveObject.from_wave_file(dirpath+"/CupTimer/sounds/low_beep.wav")
            self.high_beep = sa.WaveObject.from_wave_file(dirpath+"/CupTimer/sounds/high_beep.wav")
            self.horn = sa.WaveObject.from_wave_file(dirpath+"/CupTimer/sounds/airhorn.wav")

        self.isRunning = False
        threading.Thread.__init__(self)     # наследование функций треда

    def __del__(self):  # деструктор останавливает флаг
        self.isRunning = False

    def run(self):  # запуск обработчика событий
        self.isRunning = True
        self.Handler()

    def Handler(self):  # обработчик событий
        while self.isRunning is True:   # работает пока поднят флаг
            if eventLongBeep.isSet():   # проверяется установлено ли событие, длинный писк
                eventLongBeep.clear()   # если да - сбрасываем событие
                self.long_beep.play()   # пищим нужным тоном
            elif eventShortBeep.isSet():    # аналогично, короткий писк
                eventShortBeep.clear()
                self.short_beep.play()
            elif eventHighBeep.isSet():     # высокий писк
                eventHighBeep.clear()
                self.high_beep.play()
            elif eventLowBeep.isSet():      # низкий писк
                eventLowBeep.clear()
                self.low_beep.play()
            elif eventAirHorn.isSet():      # стартовый горн
                eventAirHorn.clear()
                self.horn.play()
        print("Music stopped")

    def Exit(self):
        print("Stopping music...")
        self.isRunning = False


def CloseProgram(w):    # при закрытии программы останавливаем таймеры и закрываем окно
    print("Stopping timers...")
    try:
        mainTimer.Exit()
    except:
        print("No main timer")
    try:
        redTimer.Exit()
    except:
        print("No red timer")
    try:
        greenTimer.Exit()
    except:
        print("No green timer")
    player.Exit()
    eventShortBeep.clear()
    eventLongBeep.clear()
    eventHighBeep.clear()
    eventLowBeep.clear()
    eventAirHorn.clear()
    # pult.Exit()
    print("Closing window...")
    Gtk.main_quit()
    gpioHandler.Exit()
    print("Program closed.")

###
'''
Маленький служебный класс для запуска Gtk в отдельном потоке.
'''
###


class GtkRunner(threading.Thread):
    def __init__(self):   # запуск гтк в отдельном треде
        threading.Thread.__init__(self)

    def run(self):
        Gtk.main()

###
'''
Класс для общения с UART и обработки входящих сообщений с пультов управления таймером.
Пока не доработан и не используется.
'''
###


class PultHandler(threading.Thread):    # класс обработки сообщений с пульта
    def __init__(self):
        self.isRunning = False
        try:
            print("Opening UART port...")
            # параметры порта (USB0 для пк, AMA0 для родного uart малины)
            self.port = serial.Serial(  # открываем порт
                                        port='/dev/ttyAMA0',
                                        baudrate=9600,
                                        parity=serial.PARITY_NONE,
                                        stopbits=serial.STOPBITS_ONE,
                                        bytesize=serial.EIGHTBITS)  # открытие порта
        except serial.SerialException:
            print("ERROR: failed to open UART")
        # список содержащий статус для каждого из пультов (None - пульт не найден, напряжение - пульт на месте)
        self.status = [5.5, 4.3, 2.1]
        self.receivedMessage = bytearray()   # полученное сообщение
        self.byte = bytearray()
        threading.Thread.__init__(self, daemon=True)  # наследование функций треда

    def __del__(self):
        print("Closing port...")
        self.isRunning = False
        try:
            self.port.close()   # закрытие порта
        except AttributeError:  # сообщение об ошибке, если не вышло
            print("Closing ERROR, no port was created.")

    def Exit(self):
        print("Closing pult...")
        print("Closing port...")
        self.isRunning = False
        try:
            self.port.close()   # закрытие порта
        except AttributeError:  # сообщение об ошибке, если не вышло
            print("Closing ERROR, no port was created.")

    def run(self):
        print("Reading port...")
        try:
            self.isRunning = True
            self.ReadPort()     # получение сообщений из порта
        except:
            print("Reading ERROR, no port was created.")    # сообщение об ошибке, если не вышло

    def ReadPort(self):     # функция читающая порт
        while self.isRunning is True:
            if self.port.isOpen:   # проверяем открыт ли uart
                # print("Getting byte")
                self.byte = self.port.read()    # поочереди выхватываем байты посылки
                print(self.byte)
                self.receivedMessage.append(ord(self.byte))
                print(self.receivedMessage)
                if hex(ord(self.byte)) == hex(0):
                    print("parsing")
                    self.ParseMessage(self.receivedMessage)
                    print("cleaning")
                    self.receivedMessage.clear()
                    print(self.receivedMessage)
            else:
                print("Port is not opened")
        print("Reading stopped")

    def ParseMessage(self, encodedLine):
        print("got message")
        for i in range(3):
            print(encodedLine[i])
        # self.decodedLine = cobs.decode(encodedLine)


###
'''
Класс работы с GPIO Raspberry Pi. К GPIO подключены кнопки Start, Pause, Reset, Shutdown,
а также энкодер с кнопкой Select.
Все кнопки подтянуты к питанию с помощью внешнего резистора, поэтому программно подтягивать их никуда не нужно.
'''
###


class GpioHandler(threading.Thread):    # класс отслеживающий состояние GPIO
    global mode, pause, finder, extremal

    def __init__(self):
        # задаем номера gpio для кнопок
        self.GpioStart = 2  # запуск таймера
        self.GpioPause = 3  # пауза таймера
        self.GpioReset = 4  # сброс таймера
        self.GpioSelect = 17    # выбор режима работы
        self.GpioEncA = 27  # установка времени с энкодера
        self.GpioEncB = 22
        self.GpioShutdown = 23  # выключение малины
        chan_list = [self.GpioSelect, self.GpioStart, self.GpioPause,
                     self.GpioReset, self.GpioShutdown]
        GPIO.setmode(GPIO.BCM)  # выбор нумерации пинов - задаем напрямую
        GPIO.setup(chan_list, GPIO.IN)   # устанавливаем все пины на вход
        GPIO.setup(self.GpioEncA, GPIO.IN, pull_up_down=GPIO.PUD_UP)    # каналы энкодера также на вход
        GPIO.setup(self.GpioEncB, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        # цепляем callback функции к изменению состояния пинов
        # применение - номер пина, что пытаемся ловить, функция - callback, сколько ждать устаканивания дребезга
        GPIO.add_event_detect(self.GpioSelect, GPIO.FALLING, callback=self.HandlerSelect, bouncetime=200)
        GPIO.add_event_detect(self.GpioStart, GPIO.FALLING, callback=self.HandlerStart, bouncetime=200)
        GPIO.add_event_detect(self.GpioPause, GPIO.FALLING, callback=self.HandlerPause, bouncetime=200)
        GPIO.add_event_detect(self.GpioReset, GPIO.FALLING, callback=self.HandlerReset, bouncetime=200)
        # GPIO.add_event_detect(self.GpioShutdown, GPIO.FALLING, callback=self.HandlerShutdown, bouncetime=200)
        self.isRunning = False  # флаг, что мы все еще слушаем GPIO (нужен для корректного завершения потока)
        threading.Thread.__init__(self, daemon=True)

    def HandlerShutdown(self, channel):
        CloseProgram()
        # TODO: проверить будет ли выполняться что то после вызова Close Program
        print("Goodbye")
        # os.system("sudo shutdown -h now")

    def HandlerStart(self, channel):    # обработка нажатия на кнопку Start
        print("Start countdown", channel)
        if mainTimer.GetIsPaused():     # если таймер был остановлен - запускаем его
            mainTimer.Resume()
        else:   # если уже тикал - принудительно завершаем чтобы перейти к следующему
            mainTimer.Force()

    def HandlerSelect(self, channel):   # обработка выбора режима
        global mode
        mainTimer.Pause()   # ставим таймер на паузу на всякий случай
        mode += 1   # выбираем следующий режим
        if mode == finder:  # если он стал искатель
            print("Finder")
            mainTimer.SetTimerList([[3, 0], [10, 0]])   # ставим таймеры - три минуты на подготовку, 10 на попытку
        elif mode == extremal:     # если стал экстремал
            print("Extremal")
            mainTimer.SetTimerList([[7, 0], [10, 0]])   # ставим таймеры - 7 минут на подготовку, 10 на попытку
        elif mode == extremalPro:  # если стал экстремал про
            print("Extremal Pro")
            mainTimer.SetTimerList([[7, 0], [10, 0]])   # ставим таймеры - 7 минут на подготовку, 10 на попытку
        elif mode > 3:
            print("Countdown")  # если просто обратный отсчет
            mode = 0    # mode изменяется в цикле 0 - 1 - 2 - 0
            mainTimer.SetTimerList([[10, 0], ])     # по умолчанию это один таймер на 10 минут и все

    def HandlerPause(self, channel):    # обработка нажатия на кнопку Pause
        print("Pause", channel)
        if mainTimer.GetIsPaused():     # если таймер стоял на паузе - запускаем его, и наоборот
            mainTimer.Resume()
        else:
            mainTimer.Pause()

    def HandlerReset(self, channel):    # обработка нажатия на кнопку Reset
        if mode == pause:   # смотрим какой стоял режим работы и ставим его параметры по умолчанию
            print("Reset pause")
            mainTimer.SetTimerList([[10, 0], ])  # по умолчанию это один таймер на 10 минут и все
        if mode == finder:
            print("Reset finder")
            mainTimer.SetTimerList([[3, 0], [10, 0]])   # ставим таймеры - три минуты на подготовку, 10 на попытку
        if mode == extremal:
            print("Reset extremal")
            mainTimer.SetTimerList([[7, 0], [10, 0]])   # ставим таймеры - 7 минут на подготовку, 10 на попытку
        if mode == extremalPro:
            print("Reset extremal pro")
            mainTimer.SetTimerList([[7, 0], [10, 0]])   # ставим таймеры - 7 минут на подготовку, 10 на попытку

    def Exit(self):
        print("Stopping GPIO handler...")
        self.isRunning = False
        GPIO.cleanup()


class EncoderCounter(threading.Thread):
    def __init__(self):
        self.GpioEncA = 27  # установка времени с энкодера
        self.GpioEncB = 22
        print("Creating encoder listener...")
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.GpioEncA, GPIO.IN)
        GPIO.setup(self.GpioEncB, GPIO.IN)
        self.isRunning = False
        self.counter = 0
        self.encAprev = GPIO.input(self.GpioEncA)
        self.encA = GPIO.input(self.GpioEncA)
        self.encB = GPIO.input(self.GpioEncB)
        threading.Thread.__init__(self, daemon=True)

    def Update(self):
        while self.isRunning:
            self.encA = GPIO.input(self.GpioEncA)
            self.encB = GPIO.input(self.GpioEncB)
            if mode == pause:
                if self.encA != self.encAprev:
                    if self.encB != self.encA:
                        # self.counter += 1
                        min = mainTimer.GetCurrentMin() # смотрим какое время было установлено
                        min += 1    # плюсуем минуту
                        if min > 99: min = 99   # обрезаем максимум
                        mainTimer.SetTimerList([[min, 0], ]) # ставим новое время
                    else:
                        # self.counter -= 1
                        min = mainTimer.GetCurrentMin() # тут аналогично, но минуту минусуем
                        min -= 1
                        if min < 1: min = 1    # и не даем уйти ниже нуля
                        mainTimer.SetTimerList([[min, 0],])
                self.encAprev = self.encA
            time.sleep(0.0001)
        print("Encoder listener stopped")

    def run(self):
        self.isRunning = True
        print("Starting encoder listener")
        self.Update()

    def Exit(self):
        print("Stopping encoder listener...")
        self.isRunning = False


mainWindow = MainWindow()  # создаем объект класса главного окна
gtkRunner = GtkRunner()

# создаем таймеры, минуты, секунды, какой таймер
redTimer = TimerClass([[2, 0], ], 'red')  # тут красный
greenTimer = TimerClass([[2, 0], ], 'green')  # тут зеленый
mainTimer = TimerClass([[3, 0], [10, 0]], 'main')   # тут главный

player = PlayMusic()    # создаем объект класса проигрывания музыки

# pult = PultHandler()    # создаем обработчик пульта

if gpio:
    gpioHandler = GpioHandler()     # обработчик нажатий на кнопки
    encoderHandler = EncoderCounter()
    encoderHandler.start()

gtkRunner.start()   # запускаем гтк
mainTimer.start()   # запускаем таймеры
# mainTimer.Resume()
player.start()  # запускаем проигрыватель музыки
# redTimer.start()
# greenTimer.start()
# pult.start()    # запускаем обработчик пульта
gtkRunner.join()    # цепляем треды к основному потоку
mainTimer.join()
# redTimer.join()
# greenTimer.join()
