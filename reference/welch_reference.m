function [frequency, psd, sample_rate, channel_count] = welch_reference(audio_file, window_seconds)
%WELCH_REFERENCE MATLAB R2026a数值参考，不创建图窗、不依赖信号处理工具箱。
% 输入 audio_file：音频路径；window_seconds：Welch窗秒数，省略为1秒。
% 输出 frequency：Hz列向量；psd：逐声道功率平均的单边FS^2/Hz列向量；
% sample_rate：解码采样率Hz；channel_count：解码声道数。
% 该参考读取全文件供交叉检查；Windows桌面成品采用独立的流式Python实现。
% GUI不依赖MATLAB。不同窗长的PSD峰值不可直接用来验证算法。
if nargin < 2
    window_seconds = 1;
end
assert(isfile(audio_file), '找不到音频文件。');
assert(isscalar(window_seconds) && isfinite(window_seconds) && window_seconds > 0);
[samples, sample_rate] = audioread(audio_file); % 全部样本，行=时间，列=声道
[sample_count, channel_count] = size(samples);
assert(sample_count >= 4 && all(isfinite(samples), 'all'), '样本无效。');
window_length = min(sample_count, 2^round(log2(window_seconds * sample_rate)));
window_length = max(4, window_length); % 实际窗长，短文件不越界
window = 0.5 - 0.5*cos(2*pi*(0:window_length-1)'/window_length); % 周期Hann窗
hop = max(1, floor(window_length/4)); % 75%重叠的帧移
last_start = sample_count - window_length + 1; % 保证尾部参与
starts = 1:hop:last_start; % 每帧起点，1基索引
if starts(end) ~= last_start
    starts(end+1) = last_start;
end
half_length = floor(window_length/2)+1; % 单边谱长度
psd = zeros(half_length, 1); % 功率累加器
for start = starts
    segment = samples(start:start+window_length-1, :); % 所有声道本帧样本
    segment = segment - mean(segment, 1); % 逐声道去直流
    transform = fft(segment .* window, window_length, 1); % 沿时间维FFT
    power = mean(abs(transform(1:half_length, :)).^2, 2); % 先平方，再跨声道平均
    power = power/(sample_rate*sum(window.^2)); % 按窗能量/Hz归一化
    if mod(window_length, 2) == 0
        power(2:end-1) = 2*power(2:end-1); % DC/Nyquist不加倍
    else
        power(2:end) = 2*power(2:end);
    end
    psd = psd + power;
end
psd = psd/numel(starts); % 帧平均
frequency = (0:half_length-1)'*sample_rate/window_length; % Hz频率轴
end
