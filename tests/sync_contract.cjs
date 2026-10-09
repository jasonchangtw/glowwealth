// Run existing sync functions against local mocks; never contacts Google/GitHub.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const html = fs.readFileSync(path.join(__dirname, '../index.html'), 'utf8');
const start = html.indexOf('            const refreshCloudFileList = async (token) => {');
const end = html.indexOf('            return (\n                <div className="p-4 md:p-8');
const calls = [], state = {}, anchors = [];
const ledger = [{id:'fixture',date:'2026-10-01',market:'TW',symbol:'2330',type:'BUY',price:'100',shares:'2',fee:'20',tax:'0',txRate:'1'}];
const dividends = [{id:'fixture-div',symbol:'2330',market:'TW',netAmount:'10'}];
let downloaded = {transactions: ledger, dividends};
const ctx = {
    transactions: ledger, dividends, Date, JSON, Blob, FormData,
    URL: { createObjectURL: blob => { state.exportBlob = blob; return 'blob:local-test'; }, revokeObjectURL() {} },
    document: {createElement: () => { const a = {click(){}}; anchors.push(a); return a; }},
    FileReader: class { readAsText(file) { this.onload({target:{result:file.text}}); } },
    confirm: () => true, alert: value => state.alert = value,
    gdriveToken: 'test-only-placeholder', selectedFileId:'fixture-file',
    jbKey:'test-only-placeholder', jbBinId:'fixture-gist',
    setTransactions: value => ctx.transactions = value,
    setDividends: value => ctx.dividends = value,
    console: {error(){}},
    fetch: async (url, options={}) => {
        calls.push({url,options});
        if(url.includes('upload/drive')) return {ok:true};
        if(url.includes('drive/v3/files?q=')) return {ok:true,json:async()=>({files:[]})};
        if(url.includes('alt=media')) return {ok:true,json:async()=>downloaded};
        if(url.endsWith('/gists') && options.method==='POST') return {ok:true,json:async()=>({id:'fixture-created'})};
        if(options.method==='PATCH') return {ok:true};
        if(url.includes('/gists/')) return {ok:true,json:async()=>({files:{'glowwealth.json':{content:JSON.stringify(downloaded)}}})};
        throw new Error('Unexpected request');
    }
};
for (const name of ['setIsSyncing','setSyncStatus','setCloudFiles','setSelectedFileId','setIsJbSyncing','setJbStatus','setJbBinId']) ctx[name] = value => state[name] = value;
vm.createContext(ctx);
vm.runInContext(html.slice(start,end)+'\nthis.api={handleSaveToCloud,handleLoadFromCloud,handleJbCreate,handleJbUpload,handleJbDownload,handleExportJson,handleImportJson};',ctx);
const checkPayload = raw => {
    const parsed = JSON.parse(raw);
    assert.deepEqual(parsed.transactions,ledger);
    assert.deepEqual(parsed.dividends,dividends);
    assert.ok(!('quotes' in parsed) && !('priceData' in parsed));
};
(async()=>{
    await ctx.api.handleJbCreate();
    const created=JSON.parse(calls.at(-1).options.body);
    assert.equal(created.public,false);
    checkPayload(created.files['glowwealth.json'].content);
    await ctx.api.handleJbUpload();
    checkPayload(JSON.parse(calls.at(-1).options.body).files['glowwealth.json'].content);
    ctx.transactions=[];ctx.dividends=[];
    await ctx.api.handleJbDownload();
    assert.deepEqual(ctx.transactions,ledger);assert.deepEqual(ctx.dividends,dividends);
    await ctx.api.handleSaveToCloud();
    const upload=calls.find(x=>x.url.includes('upload/drive'));
    checkPayload(await upload.options.body.get('file').text());
    ctx.transactions=[];ctx.dividends=[];
    await ctx.api.handleLoadFromCloud();
    assert.deepEqual(ctx.transactions,ledger);assert.deepEqual(ctx.dividends,dividends);
    ctx.api.handleExportJson();
    checkPayload(await state.exportBlob.text());
    assert.ok(anchors[0].download.startsWith('glowwealth_'));
    ctx.transactions=[];ctx.dividends=[];
    const event={target:{files:[{text:JSON.stringify(downloaded)}],value:'test-file'}};
    ctx.api.handleImportJson(event);
    assert.deepEqual(ctx.transactions,ledger);assert.deepEqual(ctx.dividends,dividends);
    assert.equal(event.target.value,'');
    console.log('PASS: existing Gist create/upload/download, Drive upload/download, JSON export/import payloads; public quotes excluded. All API calls mocked.');
})().catch(error=>{console.error(error);process.exitCode=1;});
