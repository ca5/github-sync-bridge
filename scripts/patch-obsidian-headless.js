// scripts/patch-obsidian-headless.js
const fs = require('fs');
const path = require('path');

function patchFile(filePath) {
    if (!fs.existsSync(filePath)) {
        return false;
    }

    let content = fs.readFileSync(filePath, 'utf8');
    let modified = false;

    // Patch A: Fix lock time verification float / filesystem rounding error
    const targetA = 'verify(){return this.lockTime===this.get()}';
    const replaceA = 'verify(){return Math.abs(this.lockTime-this.get())<100}';
    if (content.includes(targetA)) {
        content = content.replace(targetA, replaceA);
        modified = true;
        console.log(`[patch] Applied Patch A (lock verification precision) to ${filePath}`);
    } else if (content.includes(replaceA)) {
        console.log(`[patch] Patch A already applied to ${filePath}`);
    } else {
        console.warn(`[patch] Warning: Target A not found in ${filePath}`);
    }

    // Patch B: Proper one-shot sync: wait for ready & pending files to drain, then stop
    const oneShotLogic = `if(this.continuous){await e}else{let _w=Date.now();while(!this.ready&&Date.now()-_w<15000){await new Promise(r=>setTimeout(r,200))}let _idle=0,_end=Date.now()+60000;while(Date.now()<_end){if(this.syncing||(this.newServerFiles&&this.newServerFiles.length>0)){_idle=0}else{_idle++;if(_idle>=3)break}await new Promise(r=>setTimeout(r,200))}this.stop()}`;

    const oldTargetB1 = 'await this.requestSync(),await e';
    const oldTargetB2 = 'await this.requestSync(),(this.continuous?await e:this.stop())';

    if (content.includes(oldTargetB2)) {
        content = content.replace(oldTargetB2, `await this.requestSync();${oneShotLogic}`);
        modified = true;
        console.log(`[patch] Updated Patch B with robust one-shot sync logic in ${filePath}`);
    } else if (content.includes(oldTargetB1)) {
        content = content.replace(oldTargetB1, `await this.requestSync();${oneShotLogic}`);
        modified = true;
        console.log(`[patch] Applied Patch B with robust one-shot sync logic to ${filePath}`);
    } else if (content.includes(oneShotLogic)) {
        console.log(`[patch] Patch B already up to date in ${filePath}`);
    } else {
        console.warn(`[patch] Warning: Target B not found in ${filePath}`);
    }

    if (modified) {
        fs.writeFileSync(filePath, content, 'utf8');
        console.log(`[patch] Successfully saved patched file: ${filePath}`);
        return true;
    }
    return false;
}

function findCliJsFiles(dir) {
    const results = [];
    if (!fs.existsSync(dir)) return results;

    function walk(curr) {
        try {
            const list = fs.readdirSync(curr, { withFileTypes: true });
            for (const item of list) {
                const fullPath = path.join(curr, item.name);
                if (item.isDirectory()) {
                    if (item.name === 'obsidian-headless') {
                        const target = path.join(fullPath, 'cli.js');
                        if (fs.existsSync(target)) results.push(target);
                    } else if (item.name !== '.git') {
                        walk(fullPath);
                    }
                }
            }
        } catch (e) {
            // Ignore errors
        }
    }

    walk(dir);
    return results;
}

const nodeModulesDir = path.join(__dirname, '../node_modules');
const targets = findCliJsFiles(nodeModulesDir);

let totalPatched = 0;
for (const target of targets) {
    if (patchFile(target)) {
        totalPatched++;
    }
}
console.log(`[patch] Done. Patched ${totalPatched} of ${targets.length} file(s).`);
