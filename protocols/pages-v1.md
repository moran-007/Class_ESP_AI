# 页面模板 V0.4 实现合同（USB协议仍为v1）

固件/SDK0.4.0。本地电脑网页编辑和USB上传，不包含AI服务器。保留现有分区，页面包保存于独立教学NVS状态中；保存失败保留旧状态，不格式化。保留用户所有接线配置和已有课程脚本。

## 页面包

```json
{"schema_version":1,"width":160,"height":128,"pages":[{"id":"home","background":0,"widgets":[{"id":"title","type":"text","x":8,"y":8,"text":"你好，创客！","color":65535},{"id":"bar","type":"rect","x":8,"y":40,"width":100,"height":20,"color":2016,"filled":true}]}],"images":[]}
```

JSON本体UTF8最大8192字节；width/height整数1..320；pages1..4，总widgets最多32；images0..4，总解码图像字节最多4608。ID为ASCII字母开头，字母数字下划线，最长24；page ID全局唯一，widget ID在每页唯一，image ID全局唯一。所有对象严格字段，不接受未知字段、bool充整数、浮点、NUL或非法UTF8。

- page必需字段id/background/widgets，背景RGB565整数0..65535。
- text widget字段id/type/x/y/text/color。文字1..192 UTF8字节，禁止C0/C1控制字符（允许LF），字体沿用WQY12；坐标为字形左上角，行高16，不自动折行；起点须在canvas内，字形可裁切。
- rect widget字段id/type/x/y/width/height/color/filled，filled布尔，尺寸正整数，完整在canvas内。
- line widget字段id/type/x0/y0/x1/y1/color，两端点在canvas内。
- image widget字段id/type/x/y/asset，asset引用images ID，图像完整在canvas内。
- image对象字段id/width/height/data；每边1..48，data为严格base64的RGB565大端原始像素，解码长度精确等于width*height*2。

JSON不含脚本、网页代码或硬件操作。网页导入PNG/JPEG/WebP后在浏览器缩小为小图标、转RGB565/base64；用户导出JSON即包含素材。设备绘制前canvas尺寸必须与当前旋转后的屏幕一致。

## C++纯模型边界

新page_model.h/.cpp：namespace ai_maker。struct PageProject { JsonDocument document; std::string json; int width=0,height=0; }; bool parsePageProject(const std::string&, PageProject&, std::string& error)——失败不修改out；成功json为紧凑UTF8规范串。bool hasPage(const PageProject&,const std::string&); std::string firstPageId(const PageProject&); bool validPageText(const std::string&); bool validPageId(const std::string&); uint32_t pageCrc32(const std::string&); bool decodePageBase64(const std::string&,std::string& out,size_t max_bytes); std::string encodePageBase64(const std::string&)。

bool renderPageProject(Hardware&,const PageProject&,const std::string& page_id,const std::map<std::string,std::string>& text_overrides,std::string& error)：按顺序背景fill与widget绘制，图片大端转uint16_t后调用Hardware::bitmapDisplay(int x,int y,int w,int h,const uint16_t*)。任何驱动失败返回false，不初始化SPI，不保存状态；root DeviceCore负责生命周期和尺寸匹配。

## USB操作

device.info新增capabilities.pages/page_images/page_startup=true；limits.page_project_bytes=8192,page_upload_chunk_bytes=768,page_count=4,page_widgets=32,page_images=4,page_image_edge=48。device.status新增pages与standalone_active。

- pages.info {}：公开查询，返回saved(bool),bytes,crc32(8位小写hex),width,height,page_ids数组,startup_enabled,default_page,shown_page,standalone_active。
- pages.read {offset:整数>=0,max_bytes:1..768}：要求会话，返回offset,data(base64),total_bytes,eof；只读取保存包。
- pages.upload.begin {bytes:1..8192,crc32:8位hex字符串}：要求会话；一次一个暂存，返回upload_id。只暂存内存，不改变已保存页面。
- pages.upload.chunk {upload_id,offset,data}：data严格base64、解码1..768，offset必须等于已收到长度，不越过声明长度；返回next_offset。不能自动重试动作，SDK逐段等待匹配回执。
- pages.upload.commit {upload_id}：长度/CRC32/模型全部校验后保存完整状态；成功才替换页面包；禁用自动启动并将default_page设为第一页。返回pages.info相同字段。失败旧页面及启动策略不变，暂存可用abort丢弃。
- pages.upload.abort {upload_id}：取消当前会话暂存，幂等匹配token后返回aborted。
- pages.show {id}：不在维护模式，要求已配置屏幕且尺寸一致，按需beginDisplay，绘制页面；返回state=commanded,physical_verified=false,id。切页清空运行时文字覆盖。
- pages.text {id,text}：修改当前显示页面中指定text控件并重绘，不写NVS；正常退出时覆盖清除。
- pages.startup {enabled:bool,id:字符串可选}：保存自动启动策略，enabled=true时要求有效保存包、display配置、尺寸匹配，id缺省第一页或已选默认页；enabled=false可不传id。正常模式可用，保存本身不初始化屏幕。
- pages.clear {}：要求维护；清空页面包和启动策略，保留屏幕/舵机配置。

上传、读取和clear可在维护模式；show/text/startup不允许维护。关闭会话/超时清除暂存，不发布部分页面。read、upload等均单会话所有者；只有pages.info公开。

## 持久化与接管

旧state_version=1无页面状态可继续读取；有页面时使用state_version=2，原state值仍限制4096字节，包含现有config与pages:{slot:0或1,crc32:8位hex,startup_enabled:bool,default_page:字符串}。清空包后回到state_version=1。页面包使用NVS二进制blob（不受字符串4000字节上限限制），保存至page0/page1两个槽位。先写非活动槽位、再原子保存state中的活动槽位指针，成功后才发布内存状态并清理旧槽；任一步失败旧活动包和策略保留，不擦除旧活动槽位。启动加载所引用槽位并校验CRC/模型，错误进入维护。NVS容量不足明确STORAGE_ERROR，不格式化或改分区。

Hardware增加loadPageSlot(int)->std::string、savePageSlot(int,const std::string&)->bool、erasePageSlot(int)->bool；槽位操作不发送硬件动作。FakeHardware/本机文件适配由root接入，跨进程页槽文件为statefile.page0/statefile.page1。

启用startup后：上电（非维护）显示默认页；Python session.open先停止默认显示再获得控制；session.close/租约超时释放本会话GPIO/舵机后恢复默认页，仅屏幕参与默认程序，不驱动其他外设。maintenance.enter始终停止并禁止默认页，维护状态重启也不显示。outputs.stop在会话内只停止，不立即恢复默认页。保存新包默认关闭startup；切换屏幕尺寸/移除屏幕时也关闭不匹配的startup，保留包。恢复默认页失败要暴露driver/status与HARDWARE_ERROR，不伪装成功。

## SDK

robot.pages.info(), upload(project_or_path), download()->dict, show(id='home'), text(id,text), startup(id=None,enabled=True), clear()（SDK先进入维护，清包后仍维护）。upload支持dict、str/Path文件，紧凑UTF8序列化，先本地检查包大小、capabilities.pages后按768字节分块，CRC32用zlib；失败不自动重发，尽力abort，原始异常不被清理错误覆盖。完整模型由板端再次校验。startup和show不会自动改屏幕接线或退出维护。

SDK0.4.0，新增pages.py导出validate_project(project)->dict（严格模式，与板端一致，返回深拷贝）、load_project(path)，供本地编辑器桥接复用；客户端_pages包装调用同一校验。

## 本地网页编辑器桥接合同

editor/server.py为stdlib ThreadingHTTPServer，仅127.0.0.1，默认端口8765；新建会话token，HTML中注入API_TOKEN。每个/api调用必须X-Editor-Token，POST须application/json和同源Origin（缺失Origin允许本地Python测试携token访问）；Host校验loopback端口，不开放CORS。请求上限16384字节，无eval/exec、无任意文件路径访问。只在用户点连接后建立Robot会话，服务退出关闭它。静态文件只提供固定index.html/editor.js/editor.css。

GET /api/ports -> {ports:[{port,description}],connected:bool}；GET /api/status -> {connected,port,info,status,config,pages}，连接前其余字段null。POST /api/connect {port:'AUTO'}；POST /api/disconnect {}。POST /api/configure_display {屏幕configure各参数}保存并显式exit维护，不begin。POST /api/upload {project,show:bool,id:string可选,startup:bool}：校验、upload，若show则show选定/第一页；若startup则显式startup同页；不自动改GPIO。POST /api/show {id}；POST /api/startup {enabled,id可选}；GET /api/project -> {project:dict}下载已保存包。所有响应JSON，错误状态与message清晰，异常不泄露密钥/堆栈。

网页：本地离线HTML/JS/CSS，无CDN，canvas预览、拖拽与属性编辑、多页、文字/矩形/线段/图标、PNG/JPEG/WebP导入缩小转565、导入/导出JSON、原始JSON编辑、配置屏幕GPIO、端口选择、显式连接/断开、保存并显示、独立开机显示开关。只在按钮操作时写Flash，拖拽/预览在浏览器内。学生文字用textContent呈现，图片不接受SVG。服务器模板占位__EDITOR_TOKEN__替换成token JSON字符串。

新例子和启动器不覆盖用户01～08、_screen_settings.py等课程编辑。本地网页工具不属于AI服务器功能。

## 标准库turtle画布投送（V0.4增补）

电脑使用真正的标准库turtle窗口，完成后捕获该画布并缩放到实际屏幕；不把Tk或Python搬上ESP32。新增capabilities.display_bitmap=true、limits.display_bitmap_pixels=384。

display.bitmap {x,y,width,height,data}：要求已begin、非维护、当前会话；data是RGB565大端base64，解码长度必须正好width*height*2，一次最多384像素/768字节，矩形完整在屏内。命令直接绘制这一小块，不存NVS；成功返回state=commanded,physical_verified=false。无需整帧RAM，SDK将大画布逐条带发送。

SDK display.bitmap(x,y,width,height,pixels:bytes)发送单块；display.image(image_or_path,fit='contain',background='black')通过可选Pillow依赖缩放/裁切图像后分块发送，返回width/height/chunks/state。fit允许contain/cover，源图上限1600万像素。ai_robot.drawing.capture_turtle(screen)只捕获turtle内部Canvas，Windows优先使用Pillow窗口HWND接口；send_turtle(robot,screen)再调用image。图片投送可大于页面包8KiB，但属于内存显示，不自动保存整屏到NVS。

tests/quick/turtle_demo.py使用import turtle原生绘图，_turtle.finish()提供发送按钮/Enter和mainloop；未点发送不连接USB。发送后保持连接及心跳，关闭turtle窗口时关闭连接并恢复已启用默认页。原生窗口须存在且未最小化；不会默认截取整个桌面。Pillow通过SDK drawing可选依赖安装。
