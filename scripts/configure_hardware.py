"""Local configuration form. No connection or output is performed by saving."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_config import CONFIG_PATH, PANELS, load_config, save_config, pin_warnings

LABELS = {
    'connection': {'port':'USB串口（AUTO或COM5）'},
    'pins': {'led':'外接LED GPIO','button':'按钮 GPIO','adc':'模拟输入 GPIO','pwm':'PWM实验 GPIO'},
    'servo': {'name':'逻辑名称','pin':'信号 GPIO','min_angle':'最小角度','max_angle':'最大角度',
              'min_pulse_us':'最小脉宽（µs）','max_pulse_us':'最大脉宽（µs）'},
    'display': {'panel':'屏幕型号','sck':'SCK / SCL GPIO','mosi':'MOSI / SDA GPIO','cs':'CS GPIO',
                'dc':'DC GPIO','rst':'RST GPIO','backlight':'BLK GPIO（无控制填-1）',
                'rotation':'方向（0～3）','invert':'颜色反相','brightness':'背光亮度（0～100%）'}
}


class ConfigurationWindow:
    def __init__(self, root, path=CONFIG_PATH):
        import tkinter as tk
        from tkinter import ttk
        self.root,self.path=root,Path(path)
        self.config=load_config(self.path)
        self.fields={}
        root.title('AI小创客 · 硬件配置')
        root.geometry('640x800')
        root.minsize(600,760)
        ttk.Label(root,text='先配置串口与引脚，再运行实验',font=('Microsoft YaHei',15,'bold')).pack(anchor='w',padx=20,pady=(15,8))
        ttk.Label(root,text='保存只修改电脑配置文件；不会连接开发板或驱动外设。').pack(anchor='w',padx=20)
        notebook=ttk.Notebook(root);notebook.pack(fill='both',expand=True,padx=20,pady=12)
        for section,title in [('connection','串口'),('pins','基础GPIO'),('servo','舵机'),('display','屏幕')]:
            tab=ttk.Frame(notebook,padding=15);notebook.add(tab,text=title)
            tab.columnconfigure(1,weight=1)
            for row,(key,label) in enumerate(LABELS[section].items()):
                ttk.Label(tab,text=label).grid(row=row,column=0,sticky='w',padx=(0,15),pady=7)
                value=self.config[section][key]
                variable=tk.StringVar(value=str(value).lower() if type(value) is bool else str(value))
                self.fields[section,key]=variable
                if key=='port':
                    self.port_box=ttk.Combobox(tab,textvariable=variable);widget=self.port_box
                elif key=='panel':widget=ttk.Combobox(tab,textvariable=variable,values=PANELS,state='readonly')
                elif key=='invert':widget=ttk.Combobox(tab,textvariable=variable,values=('false','true'),state='readonly')
                else:widget=ttk.Entry(tab,textvariable=variable)
                widget.grid(row=row,column=1,sticky='ew',pady=7)
            if section=='connection':
                ttk.Button(tab,text='刷新可用USB串口',command=self.refresh_ports).grid(row=2,column=1,sticky='w',pady=12)
                self.ports_text=tk.StringVar(value='')
                ttk.Label(tab,textvariable=self.ports_text,wraplength=510).grid(row=3,column=0,columnspan=2,sticky='w')
            if section=='display':
                ttk.Label(tab,text='屏幕型号变化时请核对反相设置；ST7789通常true，ST7735通常false。\n无GPIO背光：BLK=-1，亮度=100。换线前先维护、断电。',wraplength=510).grid(row=11,column=0,columnspan=2,sticky='w',pady=6)
        ttk.Label(root,text='GPIO数字是开发板标注的IO号，不是排针第几个脚。\nLED和PWM预设可共用GPIO，仅供分别运行；按钮与LED同时使用需不同脚。',wraplength=570).pack(anchor='w',padx=20)
        self.status=tk.StringVar(value=f'配置文件：{self.path}')
        ttk.Label(root,textvariable=self.status,wraplength=570).pack(anchor='w',padx=20,pady=8)
        buttons=ttk.Frame(root);buttons.pack(fill='x',padx=20,pady=(0,15))
        ttk.Button(buttons,text='保存配置',command=self.save).pack(side='left')
        ttk.Button(buttons,text='关闭',command=root.destroy).pack(side='right')
        self.refresh_ports()

    def refresh_ports(self):
        try:
            from serial.tools import list_ports
            ports=[p for p in list_ports.comports() if p.vid is not None]
            self.port_box.configure(values=['AUTO']+[p.device for p in ports])
            self.ports_text.set('\n'.join(f'{p.device}：{p.description}' for p in ports) or '未发现USB串口；可手动填写。刷新只枚举设备，不打开串口。')
        except ImportError:
            self.ports_text.set('缺少pyserial，请运行安装Python环境.cmd；也可手动填写串口。')

    def collect(self):
        config={'schema_version':1,**{name:{} for name in LABELS}}
        for (section,key),variable in self.fields.items():
            value=variable.get().strip()
            original=self.config[section][key]
            if type(original) is bool:
                if value not in ('true','false'): raise ValueError(f'{key}须为true或false')
                value=value=='true'
            elif type(original) is int:
                try:value=int(value)
                except ValueError:raise ValueError(f'{LABELS[section][key]}须填写整数') from None
            config[section][key]=value
        return config

    def save(self):
        from tkinter import messagebox
        try:
            config=self.collect();save_config(config,self.path)
            self.config=config
            warnings=pin_warnings(config)
            self.status.set('已保存。重新启动实验文件后生效；尚未写入开发板。'+ ('\n'+'\n'.join(warnings) if warnings else ''))
        except (ValueError,OSError) as error:
            messagebox.showerror('未保存配置',str(error),parent=self.root)


def main():
    import tkinter as tk
    from tkinter import messagebox
    root=tk.Tk()
    try:ConfigurationWindow(root)
    except ValueError as error:
        root.withdraw();messagebox.showerror('配置读取失败',str(error),parent=root);root.destroy();return 1
    root.mainloop()
    return 0


if __name__=='__main__':raise SystemExit(main())
