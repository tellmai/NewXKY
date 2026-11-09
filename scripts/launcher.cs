// NewXKY.exe launcher for the runtime-based portable package.
//
// Compiled by scripts/package_runtime.py with the C# compiler that ships with
// Windows (csc.exe). It starts the bundled CPython runtime on
// portable_start.py, which shows a dialog with the traceback if startup fails,
// so a broken installation never silently does nothing.
using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

static class Program
{
    [STAThread]
    static int Main()
    {
        string root = AppDomain.CurrentDomain.BaseDirectory;
        string python = Path.Combine(root, "runtime", "pythonw.exe");
        string script = Path.Combine(root, "portable_start.py");
        if (!File.Exists(python) || !File.Exists(script))
        {
            MessageBox.Show(
                "程序文件不完整：缺少 runtime 文件夹或 portable_start.py。\n\n" +
                "1. 请重新解压整个压缩包，保留 runtime、题库 文件夹；\n" +
                "2. 不要只复制 NewXKY.exe；\n" +
                "3. 不要放在 OneDrive 等同步目录中运行。\n\n" +
                "可先双击“运行环境检查.cmd”查看缺了什么。",
                "NewXKY 启动失败",
                MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 2;
        }
        try
        {
            ProcessStartInfo info = new ProcessStartInfo(python, "\"" + script + "\"");
            info.WorkingDirectory = root;
            info.UseShellExecute = false;
            info.CreateNoWindow = true;
            Process.Start(info);
            return 0;
        }
        catch (Exception error)
        {
            MessageBox.Show(
                "无法启动 NewXKY：\n" + error.Message + "\n\n" +
                "请确认已完整解压，并且系统为 Windows 10 1809 或更新的 64 位版本。",
                "NewXKY 启动失败",
                MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 3;
        }
    }
}
