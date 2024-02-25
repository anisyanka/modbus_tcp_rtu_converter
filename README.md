# Программа управления микроскопом: Modbus TCP/RTU конвертер и web-интерфейс на базе Raspberry Pi.

# Содержание
1. [Первое включение и установка wi-fi соединения](#firststart)
2. [Настройка сервиса `modbus_converter`](#setup)
3. [Команды, поддерживаемые камерой](#cameracmd)
4. [Запуск и отображение стрима](#startstream)
5. [Полезные команды сервиса `modbus_converter`](#usefulcmd)
6. [Какие пины UART доступны для использования на RPI4?](#uartpins)
7. [Как пересобирать и обновлять код?](#swupdate)
8. [Что было установлено в образе?](#image)

## Первое включение и установка wi-fi соединения <a name="firststart"></a>
По дефолту плата RPI при загрузке пытается подключиться к следующей wi-fi сети:
```
SSID: anisyanka
PASS: CAh)z3iH
```
Чтобы настроить свою сеть и подключить RPI к wi-fi необходимо времено поднять точку доступа с вышеуказанными параметрами,
дождаться пока плата подключиться к ней и узнать IP-адрес (например, на роутере или с помощью `nmap`).
Затем залогиниться по SSH на плату и ввести следующие команды:
```
nmcli device wifi connect YOUR-SSID password "YOUR-PASSWORD"
nmcli device set wlan0 autoconnect yes
sudo reboot
```
После этого RPI всегда будет подключаться к вашей сети автоматически.

## Настройка сервиса modbus_converter  <a name="setup"></a>
Как только плата стала "онлайн", на ней автоматически запускается systemd-сервис, реализующий основную логику преобразования протоколов Modbus.
Сервис называется `modbus_converter`.
Все полезные скрипты, исполняемый файл сервиса и конфиги лежат в каталоге `/home/pi/.microscope` (обратите внимание, что в названии есть точка).

Главный конфигурационный файл, который должен редактировать пользователь  - это `/home/pi/.microscope/modbus_converter.conf`.
Формат файла - JSON. Дефолтный конфиг выглядит так:
```json
{
    "uart_device": "/dev/ttyAMA5",
    "uart_baud": "9600",
    "uart_parity": "N",
    "uart_data_bit": "8",
    "uart_stop_bit": "1",

    "modbus_port": "1502",
    "modbus_number_of_tcp_connections": "1",
    "modbus_connected_microcontroller_slave_addr": "1",
    "modbus_camera_slave_addr": "2",
    "modbus_loss_connection_timeout_ms": "1000"
}
```
`modbus_port` - порт, на котором сервис `modbus_converter` откроет TCP соединение. Этот порт нужно использовать в программе Modbus Poll или в любой другой программе, которая будет присоединяться к сервису.

**Важно:**
```
В терминах сетевого программирования сервис `modbus_converter` - это TCP-сервер.
В терминах Modbus - это slave-устройство.

Программа-клиент (например, Modbus Poll) - это Modbus-мастер. Она подключается к серверу для получения или записи данных.

С другой стороны для подключения нижестоящего микроконтроллера Modbus TCP действует, как Modbus RTU Master.
То есть одна и таже программа выступает, как slave для TCP и как master для RTU.
```
`modbus_number_of_tcp_connections` - количество возможных TCP соединений. Это для будущего использования. На данный момент поддерживается только одно соединение. Если изменить этот параметр, то сервис выдаст в лог информацию о том, что это пока не поддерживается и всё равно будет создавать только одно соединение.

`modbus_connected_microcontroller_slave_addr` - slave-адресс нижестоящего микроконтроллера. Можно установить какой угодно, так как любые присланные данные будут переданы устройству `uart_device`,
но важно, чтобы это значение не совпадало c slave-адресом камеры.

`modbus_camera_slave_addr` - slave-адрес, на который будет реагировать камера.

`modbus_loss_connection_timeout_ms` - время ожидания ответа (в милисекундах) от нижестоящего микроконтроллера. Если в течении этого промежутка времени нет ответа от устройства `uart_device`, то сервис просто начинает заново ожидать указаний по TCP.

**Если какой-либо из параметров был изменён, то необходимо перезапустить сервис, чтобы настройки вступили в силу.** См.ниже.

## Команды, поддерживаемые камерой <a name="cameracmd"></a>
Камера будет реагировать на тот адрес slave-устройства, что указали в конфиг-файле.
Команды для всех остальных адресов будут пересылаться нижестоящему микроконтроллеру.
На данный момент камера поддерживает только одну команду (один Modbus function code) - `MODBUS_FC_WRITE_SINGLE_REGISTER=0x06`
Это команда на запись аналогового вывода.
Была выбрана именно эта команда, так как в будущем можно сделать, чтобы 16-битные регистры Modbus отвечали за настройки камеры.
Например, настройка зума, баланса белого и тд.

На данный момент поддерживается только один регистр у этой команды - `CAMERA_API_LAUNCH_VIDEO_REG_ADDR=0x01`
Этот регистр отвечает за состояние видеопотока.
Значения этого регистра могут быть следующие:
```C
typedef enum {
    CAMERA_API_LAUNCH_VIDEO_4K_VALUE = 0x00,
    CAMERA_API_LAUNCH_VIDEO_1080P_VALUE = 0x01,
    CAMERA_API_LAUNCH_VIDEO_STOP_VALUE = 0x02,
} camera_api_supported_cmd_values_t;
```
Примеры Modbus-команд для камеры:
```h
0x02 0x06 0x00 0x01 0x00 0x00 <crc16> - запустить 4к видео стрим на ip адресс хоста.
0x02 0x06 0x00 0x01 0x00 0x01 <crc16> - запустить 1080p видео стрим на ip адресс хоста.
0x02 0x06 0x00 0x01 0x00 0x02 <crc16> - остановить вообще видеопоток. (Использовалось для отладки).
```

**Если камера получила неподдерживаемые значения fucntion code, регистра или значений регистров, то сервис modbus_converter вернёт соответствующие коды ошибок вышестоящей программе, приславшей неверную команду.**
**В данном случае - программе Modbus Poll.**

## Запуск и отображение стрима <a name="startstream"></a>
Как только к сервису `modbus_converter` присоединился по TCP какой-то клиент, то сервис самостоятельно определяет IP адрес этого хоста и записывает его в соответствующий конфиг-файл. Далее, как только конвертер получил команду для камеры, то он запускает соответствующий скрипт на RPI. Если запросили 4к, то запускает 4к. Если 1080p, то 1080p.
Предварительно будет считан конфиг-файл с адресом хоста. И именно на этот адрес будет посылать видеострим с помощью gstreamer.

[Как установить gstreamer на любую платформу?](https://gstreamer.freedesktop.org/documentation/installing/index.html?gi-language=c)
На плате RPI он уже установлен:

Если вы хотите запустить стрим в каком-либо разрешении, то нужно просто послать соответствующую Modbus-команду на запуск стрима.
Предварительно посылать команду "стоп" не нужно. Конвертер сам остановит старый стрим и запустит новый, если это необходимо.

Но на хосте нужно запускать соответствующие скрипты для отображения стрима руками.
Скрипты для хоста лежат в этом репозистории в директории `scripts/`. Файлы с префиксом `host_` в названии - это скрипты для запуска на хосте для отображения видеопотока.
Все остальные скрипты в этой директории не обязательны для пользователя. Они либо уже есть в образе, либо используются системой сборки для компиляции/установки.
```
 Для стрима 1080p
   На хосте запустить ./host_show_mjpg_1080p_stream_with_fps

 Для стрима 4к
    На хосте запустить ./host_show_h264_stream_with_fps
```
То есть сценарий запуска такой:
 - Сначала посылается соответствующая команда для камеры по Modbus TCP
 - Затем на хост-машине запускается соответствующий скрипт. При этом, если ранее на хосте уже был запущен какой-либо из скриптов, то его нужно остановить и только потом запускать новый.

Это нужно делать руками только лишь потому, что стримы посылаются в разных кодировках.
Для 4к используется H264. Для 1080p - MJPG. Поэтому на хосте требуется запускать разные декодеры.

vlc tcp://192.168.1.55:7001

## Полезные команды сервиса `modbus_converter` <a name="usefulcmd"></a>
```bash
# Манипуляции с запуском сервиса
service modbus_converter status
service modbus_converter start
service modbus_converter stop
service modbus_converter restart

# Тоже самое, но через systemctl
sudo systemctl status modbus_converter
sudo systemctl start modbus_converter
sudo systemctl stop modbus_converter
sudo systemctl restart modbus_converter

# Просмотр логов сервиса в режиме tail -f, показав последние 50 строк лога
sudo journalctl -a -f -n 50 -u modbus_converter # 

# Просмотр логов сервиса с момента последней загрузки системы
sudo journalctl -b -u modbus_converter
```
По дефолту сервис скомпилирован с параметром `MODBUS_CONVERTER_DEBUG=0` (см. Makefile), поэтому логов будет не очень много.
Логироваться будут только ошибки и немного теоретически полезной информации о состоянии программы.
Если нужен подробный лог происходящего, то нужно пересобрать и перезапустить сервис с 
установленным этим дефайном в значение `1`.

## Какие пины UART доступны для использования на RPI4? <a name="uartpins"></a>
https://raspberrypi.stackexchange.com/questions/45570/how-do-i-make-serial-work-on-the-raspberry-pi3-pizerow-pi4-or-later-models/107780#107780

В образе включены 3 разных uart, которые можно использовать для подключения к ним uart от нижестоящего микроконтроллера.
Здесь пины - это номер пина на 40-ко пиновой гребёнке.
```bash
# /dev/ttyAMA3 - UART3.
  PIN7 - TX
  PIN29 - RX

# /dev/ttyAMA4 - UART4.
  PIN24 - TX
  PIN21 - RX

# /dev/ttyAMA5 - UART5. <--- дефолт
  PIN32 - TX
  PIN33 - RX
```

## Как пересобирать и обновлять код? <a name="swupdate"></a>
Если в код были внесены изменения, то все они будут закомичены тут, в этот репозиторий.
Чтобы применить изменения на стороне заказчика необходимо сделать следующее:

Залогиниться по ssh на RPI и далее:
```bash
1. rm -rf ~/Microscope-controller <-- эту команду нужно выполнить один раз, так как в переданном образе в этой директории лежат исходники, но без git-а.
2. git clone https://github.com/anisyanka/Microscope-controller.git
3. cd Microscope-controller
4. make submodule_update
5. make uninstall
6. make install
```
Данные команды пересоберут свежий код и установят его куда нужно.
В дальнейшем первые четыре команды выполнять не нужно. Достаточно будет пользоваться только `git pull origin master`, а затем командой 5 и 6 для обновления, пересборки и переустановки сервиса.

## Что было установлено в образе? <a name="image"></a>
Сам образ представляет из себя дефолтный образ для RPI4 без графического интерфейса.
 * Далее были включены девайсы последовательных портов. Для этого в device tree были добавлены overlays. Они включены с помощью записи следующих строк в файл `/boot/config.txt`
```bash
enable_uart=1
dtoverlay=uart3
dtoverlay=uart4
dtoverlay=uart5
```
Они загружаются во время boot-time, поэтому команда `dtoverlay -l` не покажет их.

Также в образе включен bootlog uart. Можно подсоединить к гребенке на PIN8(tx0) и на PIN10(rx0)
uart-usb преобразватель и пользоваться этим uart, как консолью для управления платой RPI
без подключения платы к wifi и без SSH.

Посмотреть текущую конфигурацию пинов можно с помощью следующих команд:
```bash
$ pinctrl
```
либо
```bash
$ raspi-gpio get
```
Обе команды выводят информацию о текущих настройках пина. В этом случае в выводе каоманд GPIO-N - это номер gpio на процессоре. То есть **НЕ** на 40-ко пиновой гребёнке.

 * В файл `~/.bashrc` добавлены эти строки:
```bash
export LC_ALL="en_US.UTF-8"
export LANG="en_US.UTF-8"
alias ll="ls -l"
alias myip='curl ipinfo.io/ip; echo'
```

 * Пользоваьель pi добавлен в sudouser
```bash
sudo adduser pi sudo
```

 * Ограничен размер логов до 100Mb
```bash
sudo nano /etc/systemd/journald.conf
SystemMaxUse=100M
sudo systemctl restart systemd-journald
```

 * Далее были доустановлены в образ следующие программы:

**gstreamer**
```bash
sudo apt-get install libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev libgstreamer-plugins-bad1.0-dev gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav gstreamer1.0-tools gstreamer1.0-x gstreamer1.0-alsa gstreamer1.0-gl gstreamer1.0-gtk3 gstreamer1.0-qt5 gstreamer1.0-pulseaudio
```

**Программы для компиляции библиотек и конвертера**
```bash
sudo apt-get install git autoconf libtool
```

**libmodbus**
```bash
git clone https://github.com/stephane/libmodbus.git
cd ~/Microscope-controller/modbus_tcp_rtu_converter/patches
scp * pi@192.168.1.55:/home/pi/libmodbus/
cd ~/libmodbus
git apply libmodbus_tid.patch
git apply libmodbus_msglen.patch
sudo ./autogen.sh
sudo ./configure --prefix=/usr/local/
sudo make
sudo make install
```

**lsof**
```bash
sudo apt-get install lsof
```

**v4l**
```bash
apt-get install v4l-conf
```

**Flask**
```bash
# Install Flask itself
cd ~
python3 -m venv .venv
. .venv/bin/activate

cd /home/pi/Microscope-controller/web_server
pip install -r requirements.txt
deactivate

# Run server at <ip>:5000
. .venv/bin/activate
cd /home/pi/Microscope-controller/web_server
flask run --host=0.0.0.0 --debug --app microscope_server.py
```

sudo lsof -iTCP -sTCP:LISTEN

#!/bin/sh
for pid in $(lsof -iTCP -sTCP:LISTEN | grep 5000 | awk -F' ' '{print $2}'); do kill -9 $pid 2>/dev/null; done
