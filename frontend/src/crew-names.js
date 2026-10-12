const firstNames=['Aarav','Aditi','Akash','Anaya','Arjun','Diya','Ishaan','Kavya','Mira','Neel','Nila','Rohan','Tara','Vihaan'];
const lastNames=['Bose','Chen','Das','Iyer','Kapoor','Malik','Mehta','Nair','Patel','Rao','Sen','Shah','Verma','Wong'];

function randomIndex(length){
  if(globalThis.crypto?.getRandomValues){const value=new Uint32Array(1);globalThis.crypto.getRandomValues(value);return value[0]%length;}
  return Math.floor(Math.random()*length);
}

export function randomCrewName(usedNames=[]){
  const used=new Set(usedNames.map(value=>String(value||'').trim().toLocaleLowerCase()));
  for(let attempt=0;attempt<200;attempt++){
    const candidate=`${firstNames[randomIndex(firstNames.length)]} ${lastNames[randomIndex(lastNames.length)]}`;
    if(!used.has(candidate.toLocaleLowerCase()))return candidate;
  }
  return `Crew ${Date.now().toString(36).toUpperCase()}`;
}
